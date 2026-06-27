"""
Test V4 Features: 2FA, Social/Leaderboard, Push Notifications
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuthentication:
    """Test authentication endpoints"""
    
    def test_admin_login(self):
        """Test admin login with correct credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@trading.com", "password": "Admin@123456"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        # Check if user data is returned (not requires_2fa since 2FA is not enabled)
        assert "email" in data or "requires_2fa" in data
        print(f"✓ Admin login successful: {data.get('email', 'requires_2fa')}")
        return response.cookies


class Test2FAEndpoints:
    """Test Two-Factor Authentication endpoints"""
    
    @pytest.fixture
    def auth_cookies(self):
        """Get authenticated session cookies"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@trading.com", "password": "Admin@123456"}
        )
        return response.cookies
    
    def test_2fa_status(self, auth_cookies):
        """Test GET /api/auth/2fa/status"""
        response = requests.get(
            f"{BASE_URL}/api/auth/2fa/status",
            cookies=auth_cookies
        )
        assert response.status_code == 200, f"2FA status failed: {response.text}"
        data = response.json()
        assert "enabled" in data
        print(f"✓ 2FA status: enabled={data['enabled']}, backup_codes_remaining={data.get('backup_codes_remaining', 0)}")
    
    def test_2fa_setup(self, auth_cookies):
        """Test POST /api/auth/2fa/setup"""
        response = requests.post(
            f"{BASE_URL}/api/auth/2fa/setup",
            cookies=auth_cookies
        )
        assert response.status_code == 200, f"2FA setup failed: {response.text}"
        data = response.json()
        assert "qr_code" in data, "QR code not in response"
        assert "secret" in data, "Secret not in response"
        assert "backup_codes" in data, "Backup codes not in response"
        assert len(data["backup_codes"]) == 8, f"Expected 8 backup codes, got {len(data['backup_codes'])}"
        print(f"✓ 2FA setup successful: secret={data['secret'][:8]}..., backup_codes={len(data['backup_codes'])}")


class TestSocialEndpoints:
    """Test Social/Leaderboard endpoints"""
    
    @pytest.fixture
    def auth_cookies(self):
        """Get authenticated session cookies"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@trading.com", "password": "Admin@123456"}
        )
        return response.cookies
    
    def test_leaderboard(self, auth_cookies):
        """Test GET /api/social/leaderboard"""
        response = requests.get(
            f"{BASE_URL}/api/social/leaderboard",
            cookies=auth_cookies
        )
        assert response.status_code == 200, f"Leaderboard failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Leaderboard should return a list"
        print(f"✓ Leaderboard returned {len(data)} traders")
        if data:
            trader = data[0]
            assert "user_id" in trader or "user_name" in trader
            print(f"  Top trader: {trader.get('user_name', 'N/A')}")
    
    def test_global_feed(self, auth_cookies):
        """Test GET /api/social/feed/global"""
        response = requests.get(
            f"{BASE_URL}/api/social/feed/global?limit=10",
            cookies=auth_cookies
        )
        assert response.status_code == 200, f"Global feed failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Global feed should return a list"
        print(f"✓ Global feed returned {len(data)} activities")
    
    def test_my_feed(self, auth_cookies):
        """Test GET /api/social/feed"""
        response = requests.get(
            f"{BASE_URL}/api/social/feed?limit=10",
            cookies=auth_cookies
        )
        assert response.status_code == 200, f"My feed failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "My feed should return a list"
        print(f"✓ My feed returned {len(data)} activities")
    
    def test_followers(self, auth_cookies):
        """Test GET /api/social/followers"""
        response = requests.get(
            f"{BASE_URL}/api/social/followers",
            cookies=auth_cookies
        )
        assert response.status_code == 200, f"Followers failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Followers should return a list"
        print(f"✓ Followers: {len(data)}")
    
    def test_following(self, auth_cookies):
        """Test GET /api/social/following"""
        response = requests.get(
            f"{BASE_URL}/api/social/following",
            cookies=auth_cookies
        )
        assert response.status_code == 200, f"Following failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Following should return a list"
        print(f"✓ Following: {len(data)}")
    
    def test_my_profile(self, auth_cookies):
        """Test GET /api/social/profile"""
        response = requests.get(
            f"{BASE_URL}/api/social/profile",
            cookies=auth_cookies
        )
        assert response.status_code == 200, f"My profile failed: {response.text}"
        data = response.json()
        assert "user_id" in data or "name" in data or "email" in data
        print(f"✓ My profile: {data.get('name', data.get('email', 'N/A'))}")


class TestNotificationEndpoints:
    """Test Push Notification endpoints"""
    
    @pytest.fixture
    def auth_cookies(self):
        """Get authenticated session cookies"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@trading.com", "password": "Admin@123456"}
        )
        return response.cookies
    
    def test_notification_status(self, auth_cookies):
        """Test GET /api/notifications/status"""
        response = requests.get(
            f"{BASE_URL}/api/notifications/status",
            cookies=auth_cookies
        )
        assert response.status_code == 200, f"Notification status failed: {response.text}"
        data = response.json()
        assert "enabled" in data
        print(f"✓ Push notification status: enabled={data['enabled']}")
    
    def test_notification_subscribe(self, auth_cookies):
        """Test POST /api/notifications/subscribe"""
        response = requests.post(
            f"{BASE_URL}/api/notifications/subscribe",
            json={"endpoint": "https://test.example.com", "enabled": True},
            cookies=auth_cookies
        )
        assert response.status_code == 200, f"Subscribe failed: {response.text}"
        data = response.json()
        assert "message" in data
        print(f"✓ Push notification subscribe: {data['message']}")
    
    def test_notification_unsubscribe(self, auth_cookies):
        """Test DELETE /api/notifications/unsubscribe"""
        response = requests.delete(
            f"{BASE_URL}/api/notifications/unsubscribe",
            cookies=auth_cookies
        )
        assert response.status_code == 200, f"Unsubscribe failed: {response.text}"
        data = response.json()
        assert "message" in data
        print(f"✓ Push notification unsubscribe: {data['message']}")


class TestHealthAndVersion:
    """Test health and version endpoints"""
    
    def test_health(self):
        """Test GET /api/health"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print(f"✓ Health check: {data}")
    
    def test_version(self):
        """Test GET /api/version"""
        response = requests.get(f"{BASE_URL}/api/version")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "features" in data
        # Check V4 features are listed
        features = data.get("features", [])
        assert "2fa" in features, "2FA feature not listed"
        assert "social" in features, "Social feature not listed"
        print(f"✓ Version: {data['version']}, Features: {features}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
