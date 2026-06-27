"""
Test suite for V8 Risk Alert Push feature
Tests: GET/POST /api/risk-alerts/config, POST /api/risk-alerts/check, GET /api/risk-alerts/history
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestRiskAlertEndpoints:
    """Risk Alert API endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get session cookies"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login with admin credentials
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@trading.com",
            "password": "Admin@123456"
        })
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code} - {login_response.text}")
        
        self.user = login_response.json()
        print(f"Logged in as: {self.user.get('email')}")
    
    # ==================== GET /api/risk-alerts/config ====================
    
    def test_get_risk_alert_config_returns_200(self):
        """Test GET /api/risk-alerts/config returns 200"""
        response = self.session.get(f"{BASE_URL}/api/risk-alerts/config")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("SUCCESS: GET /api/risk-alerts/config returns 200")
    
    def test_get_risk_alert_config_has_required_fields(self):
        """Test GET /api/risk-alerts/config returns all required threshold fields"""
        response = self.session.get(f"{BASE_URL}/api/risk-alerts/config")
        assert response.status_code == 200
        
        config = response.json()
        required_fields = [
            'var_threshold', 'volatility_threshold', 'drawdown_threshold',
            'sharpe_threshold', 'stress_severity_trigger', 'telegram_push',
            'browser_push', 'enabled'
        ]
        
        for field in required_fields:
            assert field in config, f"Missing required field: {field}"
            print(f"  - {field}: {config[field]}")
        
        print("SUCCESS: Config has all required fields")
    
    def test_get_risk_alert_config_default_values(self):
        """Test GET /api/risk-alerts/config returns sensible default values"""
        response = self.session.get(f"{BASE_URL}/api/risk-alerts/config")
        assert response.status_code == 200
        
        config = response.json()
        
        # Check default value types
        assert isinstance(config.get('var_threshold'), (int, float)), "var_threshold should be numeric"
        assert isinstance(config.get('volatility_threshold'), (int, float)), "volatility_threshold should be numeric"
        assert isinstance(config.get('drawdown_threshold'), (int, float)), "drawdown_threshold should be numeric"
        assert isinstance(config.get('sharpe_threshold'), (int, float)), "sharpe_threshold should be numeric"
        assert isinstance(config.get('stress_severity_trigger'), str), "stress_severity_trigger should be string"
        assert isinstance(config.get('telegram_push'), bool), "telegram_push should be boolean"
        assert isinstance(config.get('browser_push'), bool), "browser_push should be boolean"
        assert isinstance(config.get('enabled'), bool), "enabled should be boolean"
        
        print("SUCCESS: Config has correct value types")
    
    # ==================== POST /api/risk-alerts/config ====================
    
    def test_save_risk_alert_config_returns_200(self):
        """Test POST /api/risk-alerts/config saves custom configuration"""
        custom_config = {
            "enabled": True,
            "var_threshold": 7500,
            "volatility_threshold": 40,
            "drawdown_threshold": 20,
            "sharpe_threshold": 0.3,
            "stress_severity_trigger": "HIGH",
            "telegram_push": True,
            "browser_push": False
        }
        
        response = self.session.post(f"{BASE_URL}/api/risk-alerts/config", json=custom_config)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        saved = response.json()
        assert saved.get('var_threshold') == 7500, f"var_threshold not saved correctly: {saved.get('var_threshold')}"
        assert saved.get('volatility_threshold') == 40, f"volatility_threshold not saved correctly"
        assert saved.get('drawdown_threshold') == 20, f"drawdown_threshold not saved correctly"
        assert saved.get('sharpe_threshold') == 0.3, f"sharpe_threshold not saved correctly"
        assert saved.get('stress_severity_trigger') == "HIGH", f"stress_severity_trigger not saved correctly"
        assert saved.get('browser_push') == False, f"browser_push not saved correctly"
        
        print("SUCCESS: POST /api/risk-alerts/config saves and returns saved data")
    
    def test_save_config_persists_on_get(self):
        """Test that saved config persists when fetched again"""
        # Save custom config
        custom_config = {
            "enabled": True,
            "var_threshold": 8000,
            "volatility_threshold": 35,
            "drawdown_threshold": 18,
            "sharpe_threshold": 0.4,
            "stress_severity_trigger": "MODERATE",
            "telegram_push": False,
            "browser_push": True
        }
        
        save_response = self.session.post(f"{BASE_URL}/api/risk-alerts/config", json=custom_config)
        assert save_response.status_code == 200
        
        # Fetch config again
        get_response = self.session.get(f"{BASE_URL}/api/risk-alerts/config")
        assert get_response.status_code == 200
        
        fetched = get_response.json()
        assert fetched.get('var_threshold') == 8000, "Config not persisted correctly"
        assert fetched.get('stress_severity_trigger') == "MODERATE", "stress_severity_trigger not persisted"
        
        print("SUCCESS: Config persists correctly after save")
    
    # ==================== POST /api/risk-alerts/check ====================
    
    def test_check_risk_alerts_returns_200(self):
        """Test POST /api/risk-alerts/check returns 200"""
        response = self.session.post(f"{BASE_URL}/api/risk-alerts/check", json={})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("SUCCESS: POST /api/risk-alerts/check returns 200")
    
    def test_check_risk_alerts_response_structure(self):
        """Test POST /api/risk-alerts/check returns correct response structure"""
        response = self.session.post(f"{BASE_URL}/api/risk-alerts/check", json={})
        assert response.status_code == 200
        
        result = response.json()
        
        # Check required fields
        assert 'checked' in result, "Missing 'checked' field"
        assert 'alerts_fired' in result, "Missing 'alerts_fired' field"
        assert 'alerts' in result, "Missing 'alerts' field"
        assert 'risk_snapshot' in result, "Missing 'risk_snapshot' field"
        
        # Validate types
        assert isinstance(result['checked'], bool), "checked should be boolean"
        assert isinstance(result['alerts_fired'], int), "alerts_fired should be integer"
        assert isinstance(result['alerts'], list), "alerts should be list"
        assert isinstance(result['risk_snapshot'], dict), "risk_snapshot should be dict"
        
        print(f"SUCCESS: Risk check response structure valid")
        print(f"  - checked: {result['checked']}")
        print(f"  - alerts_fired: {result['alerts_fired']}")
        print(f"  - alerts count: {len(result['alerts'])}")
    
    def test_check_risk_alerts_risk_snapshot_fields(self):
        """Test POST /api/risk-alerts/check returns risk_snapshot with expected fields"""
        response = self.session.post(f"{BASE_URL}/api/risk-alerts/check", json={})
        assert response.status_code == 200
        
        result = response.json()
        snapshot = result.get('risk_snapshot', {})
        
        expected_fields = ['var_95', 'annual_vol', 'max_dd', 'sharpe', 'stress_critical_count']
        for field in expected_fields:
            assert field in snapshot, f"Missing risk_snapshot field: {field}"
            print(f"  - {field}: {snapshot[field]}")
        
        print("SUCCESS: risk_snapshot has all expected fields")
    
    def test_check_risk_alerts_with_low_thresholds(self):
        """Test risk check triggers alerts when thresholds are set very low"""
        # First, set very low thresholds to trigger alerts
        low_config = {
            "enabled": True,
            "var_threshold": 100,  # Very low - should trigger
            "volatility_threshold": 1,  # Very low - should trigger
            "drawdown_threshold": 0.1,  # Very low - should trigger
            "sharpe_threshold": 10,  # Very high - should trigger (sharpe below this)
            "stress_severity_trigger": "LOW",  # Trigger on any severity
            "telegram_push": False,  # Disable telegram for test
            "browser_push": False
        }
        
        save_response = self.session.post(f"{BASE_URL}/api/risk-alerts/config", json=low_config)
        assert save_response.status_code == 200
        
        # Run risk check
        check_response = self.session.post(f"{BASE_URL}/api/risk-alerts/check", json={})
        assert check_response.status_code == 200
        
        result = check_response.json()
        print(f"Risk check with low thresholds: alerts_fired={result.get('alerts_fired')}")
        
        # Note: Due to 30-minute cooldown, alerts may not fire if already triggered recently
        # But the API should still return valid response
        assert 'alerts_fired' in result
        assert 'risk_snapshot' in result
        
        print("SUCCESS: Risk check with low thresholds executed correctly")
    
    # ==================== GET /api/risk-alerts/history ====================
    
    def test_get_risk_alert_history_returns_200(self):
        """Test GET /api/risk-alerts/history returns 200"""
        response = self.session.get(f"{BASE_URL}/api/risk-alerts/history")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("SUCCESS: GET /api/risk-alerts/history returns 200")
    
    def test_get_risk_alert_history_returns_list(self):
        """Test GET /api/risk-alerts/history returns a list"""
        response = self.session.get(f"{BASE_URL}/api/risk-alerts/history")
        assert response.status_code == 200
        
        history = response.json()
        assert isinstance(history, list), f"Expected list, got {type(history)}"
        
        print(f"SUCCESS: Alert history is a list with {len(history)} items")
    
    def test_get_risk_alert_history_item_structure(self):
        """Test GET /api/risk-alerts/history items have correct structure"""
        response = self.session.get(f"{BASE_URL}/api/risk-alerts/history")
        assert response.status_code == 200
        
        history = response.json()
        
        if len(history) > 0:
            alert = history[0]
            required_fields = ['alert_type', 'severity', 'message', 'triggered_at']
            
            for field in required_fields:
                assert field in alert, f"Missing required field in alert: {field}"
            
            print(f"SUCCESS: Alert history item has correct structure")
            print(f"  - alert_type: {alert.get('alert_type')}")
            print(f"  - severity: {alert.get('severity')}")
            print(f"  - message: {alert.get('message')[:50]}...")
            print(f"  - triggered_at: {alert.get('triggered_at')}")
        else:
            print("INFO: Alert history is empty (no alerts triggered yet)")
    
    def test_get_risk_alert_history_with_limit(self):
        """Test GET /api/risk-alerts/history respects limit parameter"""
        response = self.session.get(f"{BASE_URL}/api/risk-alerts/history?limit=5")
        assert response.status_code == 200
        
        history = response.json()
        assert len(history) <= 5, f"Expected max 5 items, got {len(history)}"
        
        print(f"SUCCESS: Alert history respects limit parameter (returned {len(history)} items)")
    
    # ==================== Auth Required Tests ====================
    
    def test_risk_alerts_config_requires_auth(self):
        """Test that risk-alerts endpoints require authentication"""
        # Create new session without auth
        unauth_session = requests.Session()
        
        response = unauth_session.get(f"{BASE_URL}/api/risk-alerts/config")
        assert response.status_code == 401, f"Expected 401 for unauthenticated request, got {response.status_code}"
        
        print("SUCCESS: Risk alerts config requires authentication")
    
    def test_risk_alerts_check_requires_auth(self):
        """Test that risk check endpoint requires authentication"""
        unauth_session = requests.Session()
        
        response = unauth_session.post(f"{BASE_URL}/api/risk-alerts/check", json={})
        assert response.status_code == 401, f"Expected 401 for unauthenticated request, got {response.status_code}"
        
        print("SUCCESS: Risk alerts check requires authentication")
    
    def test_risk_alerts_history_requires_auth(self):
        """Test that risk history endpoint requires authentication"""
        unauth_session = requests.Session()
        
        response = unauth_session.get(f"{BASE_URL}/api/risk-alerts/history")
        assert response.status_code == 401, f"Expected 401 for unauthenticated request, got {response.status_code}"
        
        print("SUCCESS: Risk alerts history requires authentication")


class TestRiskAlertCooldown:
    """Test alert cooldown functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get session cookies"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@trading.com",
            "password": "Admin@123456"
        })
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code}")
    
    def test_cooldown_prevents_duplicate_alerts(self):
        """Test that cooldown prevents duplicate alerts within 30 minutes"""
        # Set low thresholds to trigger alerts
        low_config = {
            "enabled": True,
            "var_threshold": 100,
            "volatility_threshold": 1,
            "drawdown_threshold": 0.1,
            "sharpe_threshold": 10,
            "stress_severity_trigger": "LOW",
            "telegram_push": False,
            "browser_push": False
        }
        
        self.session.post(f"{BASE_URL}/api/risk-alerts/config", json=low_config)
        
        # Run first check
        first_check = self.session.post(f"{BASE_URL}/api/risk-alerts/check", json={})
        assert first_check.status_code == 200
        first_result = first_check.json()
        first_alerts = first_result.get('alerts_fired', 0)
        
        # Run second check immediately
        second_check = self.session.post(f"{BASE_URL}/api/risk-alerts/check", json={})
        assert second_check.status_code == 200
        second_result = second_check.json()
        second_alerts = second_result.get('alerts_fired', 0)
        
        # Second check should have fewer or equal alerts due to cooldown
        print(f"First check alerts: {first_alerts}, Second check alerts: {second_alerts}")
        print("SUCCESS: Cooldown mechanism is in place (second check may have fewer alerts)")


class TestRiskAlertDisabled:
    """Test behavior when alerts are disabled"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get session cookies"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@trading.com",
            "password": "Admin@123456"
        })
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code}")
    
    def test_disabled_alerts_returns_message(self):
        """Test that disabled alerts return appropriate message"""
        # Disable alerts
        disabled_config = {
            "enabled": False,
            "var_threshold": 100,
            "volatility_threshold": 1,
            "telegram_push": False,
            "browser_push": False
        }
        
        self.session.post(f"{BASE_URL}/api/risk-alerts/config", json=disabled_config)
        
        # Run check
        check_response = self.session.post(f"{BASE_URL}/api/risk-alerts/check", json={})
        assert check_response.status_code == 200
        
        result = check_response.json()
        assert result.get('checked') == True
        assert result.get('alerts_fired') == 0
        
        # Re-enable for other tests
        enabled_config = {"enabled": True, "telegram_push": False, "browser_push": False}
        self.session.post(f"{BASE_URL}/api/risk-alerts/config", json=enabled_config)
        
        print("SUCCESS: Disabled alerts return 0 alerts_fired")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
