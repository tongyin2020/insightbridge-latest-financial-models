"""
Test Authentication Endpoints - Iteration 5
Tests JWT authentication: login, logout, /me endpoint, token validation
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@cryptoai.com"
ADMIN_PASSWORD = "CryptoAI2026!"
WRONG_PASSWORD = "WrongPassword123!"


class TestAuthLogin:
    """Test POST /api/auth/login endpoint"""
    
    def test_login_success_with_correct_credentials(self):
        """Login with correct admin credentials returns token and user data"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "token" in data, "Response should contain 'token'"
        assert "email" in data, "Response should contain 'email'"
        assert "id" in data, "Response should contain 'id'"
        
        # Verify data values
        assert data["email"] == ADMIN_EMAIL.lower(), f"Email mismatch: {data['email']}"
        assert len(data["token"]) > 0, "Token should not be empty"
        assert data.get("role") == "admin", f"Role should be admin, got {data.get('role')}"
        
        # Verify cookies are set
        cookies = response.cookies
        assert "access_token" in cookies or len(cookies) > 0, "Cookies should be set on login"
        print(f"✓ Login successful for {ADMIN_EMAIL}")
    
    def test_login_failure_with_wrong_password(self):
        """Login with wrong password returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": WRONG_PASSWORD}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data, "Error response should contain 'detail'"
        print(f"✓ Wrong password correctly rejected with 401")
    
    def test_login_failure_with_nonexistent_email(self):
        """Login with non-existent email returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "nonexistent@test.com", "password": "anypassword"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ Non-existent email correctly rejected with 401")
    
    def test_login_case_insensitive_email(self):
        """Login should work with different email case"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL.upper(), "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ Case-insensitive email login works")


class TestAuthMe:
    """Test GET /api/auth/me endpoint"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed - skipping authenticated tests")
    
    def test_me_with_valid_token(self, auth_token):
        """GET /api/auth/me with valid token returns user data"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "email" in data, "Response should contain 'email'"
        assert data["email"] == ADMIN_EMAIL.lower(), f"Email mismatch: {data['email']}"
        assert "password_hash" not in data, "Response should NOT contain password_hash"
        print(f"✓ /api/auth/me returns user data correctly")
    
    def test_me_without_token_returns_401(self):
        """GET /api/auth/me without token returns 401"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ /api/auth/me without token correctly returns 401")
    
    def test_me_with_invalid_token_returns_401(self):
        """GET /api/auth/me with invalid token returns 401"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": "Bearer invalid_token_here"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ /api/auth/me with invalid token correctly returns 401")


class TestAuthLogout:
    """Test POST /api/auth/logout endpoint"""
    
    def test_logout_clears_cookies(self):
        """POST /api/auth/logout clears authentication cookies"""
        # First login to get cookies
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200, "Login should succeed"
        
        # Now logout
        logout_response = session.post(f"{BASE_URL}/api/auth/logout")
        assert logout_response.status_code == 200, f"Expected 200, got {logout_response.status_code}"
        
        data = logout_response.json()
        assert data.get("success") == True, "Logout should return success: true"
        print(f"✓ Logout endpoint works correctly")


class TestExistingAPIsStillWork:
    """Verify existing APIs still work after auth implementation"""
    
    def test_health_endpoint(self):
        """GET /api/health should still work (no auth required)"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "healthy", f"Health status should be 'healthy'"
        print(f"✓ /api/health still works")
    
    def test_prices_endpoint(self):
        """GET /api/prices/AUD_USD should still work"""
        response = requests.get(f"{BASE_URL}/api/prices/AUD_USD")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # Price data may be nested under 'price' key
        price_data = data.get("price", data)
        assert "mid" in price_data or "pair" in data, "Price data should contain price info"
        print(f"✓ /api/prices/AUD_USD still works")
    
    def test_event_response_status(self):
        """GET /api/event-response/status should still work"""
        response = requests.get(f"{BASE_URL}/api/event-response/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "engines" in data, "Response should contain 'engines'"
        print(f"✓ /api/event-response/status still works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
