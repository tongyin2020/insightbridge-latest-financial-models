"""
Test V5 Features: Bond Analytics, Auto-Execute, Backend Refactoring Verification
Tests all new endpoints and verifies existing APIs still work after refactoring.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthAndBasicEndpoints:
    """Health check and basic endpoint tests"""
    
    def test_health_endpoint(self):
        """Test /api/health returns all features including bond_analytics and auto_execute"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "features" in data
        
        # Verify new V5 features are listed
        features = data["features"]
        assert "bond_analytics" in features, "bond_analytics feature missing"
        assert "auto_execute" in features, "auto_execute feature missing"
        assert "paper_trading" in features
        assert "multi_asset" in features
        assert "strategy_marketplace" in features
        assert "2fa" in features
        assert "social" in features
        print(f"Health check passed. Features: {features}")
    
    def test_root_endpoint(self):
        """Test /api/ root endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data or "message" in data
        print(f"Root endpoint: {data}")


class TestAuthFlow:
    """Authentication tests"""
    
    @pytest.fixture
    def session(self):
        return requests.Session()
    
    def test_login_success(self, session):
        """Test admin login with correct credentials"""
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@trading.com",
            "password": "Admin@123456"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        
        data = response.json()
        # Check if 2FA is required or direct login
        if data.get("requires_2fa"):
            print("2FA required for this account")
        else:
            assert data["email"] == "admin@trading.com"
            assert data["role"] == "admin"
            print(f"Login successful: {data['email']}")
    
    def test_login_invalid_credentials(self, session):
        """Test login with wrong password"""
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@trading.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print("Invalid credentials correctly rejected")


class TestBondAnalytics:
    """Bond Analytics API tests - New V5 feature"""
    
    @pytest.fixture
    def auth_session(self):
        session = requests.Session()
        session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@trading.com",
            "password": "Admin@123456"
        })
        return session
    
    def test_bond_analytics_endpoint(self, auth_session):
        """Test /api/market/bond-analytics returns yield curve, risk metrics, inflation, signals"""
        response = auth_session.get(f"{BASE_URL}/api/market/bond-analytics")
        assert response.status_code == 200, f"Bond analytics failed: {response.text}"
        
        data = response.json()
        
        # Verify yield_curve data
        assert "yield_curve" in data, "yield_curve missing"
        yield_curve = data["yield_curve"]
        assert "slope_10y_3m" in yield_curve, "slope_10y_3m missing"
        assert "is_inverted" in yield_curve, "is_inverted missing"
        print(f"Yield curve slope: {yield_curve.get('slope_10y_3m')}, Inverted: {yield_curve.get('is_inverted')}")
        
        # Verify risk_metrics data
        assert "risk_metrics" in data, "risk_metrics missing"
        risk_metrics = data["risk_metrics"]
        assert "vix" in risk_metrics, "VIX missing"
        assert "dollar_index" in risk_metrics, "dollar_index missing"
        print(f"VIX: {risk_metrics.get('vix')}, DXY: {risk_metrics.get('dollar_index')}")
        
        # Verify inflation data
        assert "inflation" in data, "inflation missing"
        inflation = data["inflation"]
        assert "real_yield" in inflation, "real_yield missing"
        assert "breakeven_inflation" in inflation, "breakeven_inflation missing"
        print(f"Real yield: {inflation.get('real_yield')}, BEI: {inflation.get('breakeven_inflation')}")
        
        # Verify signals
        assert "signals" in data, "signals missing"
        signals = data["signals"]
        print(f"Signals: {signals}")


class TestExistingAPIsAfterRefactoring:
    """Verify all existing APIs still work after backend refactoring"""
    
    @pytest.fixture
    def auth_session(self):
        session = requests.Session()
        session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@trading.com",
            "password": "Admin@123456"
        })
        return session
    
    def test_market_current(self, auth_session):
        """Test /api/market/current still works"""
        response = auth_session.get(f"{BASE_URL}/api/market/current")
        assert response.status_code == 200, f"Market current failed: {response.text}"
        data = response.json()
        assert "wti_price" in data or "bond_yield" in data
        print(f"Market current: WTI={data.get('wti_price')}, Bond={data.get('bond_yield')}")
    
    def test_strategy_config(self, auth_session):
        """Test /api/strategy/config still works"""
        response = auth_session.get(f"{BASE_URL}/api/strategy/config")
        assert response.status_code == 200, f"Strategy config failed: {response.text}"
        data = response.json()
        assert "strategy_type" in data
        assert "ispread_upper" in data
        print(f"Strategy config: {data.get('strategy_type')}")
    
    def test_paper_trading_portfolio(self, auth_session):
        """Test /api/paper-trading/portfolio still works"""
        response = auth_session.get(f"{BASE_URL}/api/paper-trading/portfolio")
        assert response.status_code == 200, f"Paper trading portfolio failed: {response.text}"
        data = response.json()
        assert "cash" in data or "positions" in data or "total_value" in data
        print(f"Paper trading portfolio retrieved")
    
    def test_backtest_run(self, auth_session):
        """Test /api/backtest/run still works"""
        response = auth_session.post(f"{BASE_URL}/api/backtest/run", json={
            "strategy_type": "MEAN_REVERSION",
            "start_date": "2024-01-01",
            "end_date": "2024-06-01",
            "initial_capital": 100000
        })
        assert response.status_code == 200, f"Backtest run failed: {response.text}"
        data = response.json()
        assert "total_return" in data or "sharpe_ratio" in data or "trades" in data
        print(f"Backtest completed")
    
    def test_social_leaderboard(self, auth_session):
        """Test /api/social/leaderboard still works"""
        response = auth_session.get(f"{BASE_URL}/api/social/leaderboard")
        assert response.status_code == 200, f"Social leaderboard failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"Leaderboard has {len(data)} entries")
    
    def test_marketplace_strategies(self, auth_session):
        """Test /api/marketplace/strategies still works"""
        response = auth_session.get(f"{BASE_URL}/api/marketplace/strategies")
        assert response.status_code == 200, f"Marketplace strategies failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"Marketplace has {len(data)} strategies")


class TestAutoExecuteFeature:
    """Auto-Execute feature tests - New V5 feature"""
    
    @pytest.fixture
    def auth_session(self):
        session = requests.Session()
        session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@trading.com",
            "password": "Admin@123456"
        })
        return session
    
    def test_auto_execute_logs(self, auth_session):
        """Test /api/auto-execute/logs endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/auto-execute/logs")
        assert response.status_code == 200, f"Auto-execute logs failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"Auto-execute logs: {len(data)} entries")
    
    def test_marketplace_subscriptions(self, auth_session):
        """Test /api/marketplace/subscriptions endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/marketplace/subscriptions")
        assert response.status_code == 200, f"Subscriptions failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"User has {len(data)} subscriptions")


class Test2FAEndpoints:
    """2FA endpoint tests"""
    
    @pytest.fixture
    def auth_session(self):
        session = requests.Session()
        session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@trading.com",
            "password": "Admin@123456"
        })
        return session
    
    def test_2fa_status(self, auth_session):
        """Test /api/auth/2fa/status endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/auth/2fa/status")
        assert response.status_code == 200, f"2FA status failed: {response.text}"
        data = response.json()
        assert "enabled" in data
        print(f"2FA enabled: {data.get('enabled')}")


class TestSystemEndpoints:
    """System state and control endpoints"""
    
    @pytest.fixture
    def auth_session(self):
        session = requests.Session()
        session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@trading.com",
            "password": "Admin@123456"
        })
        return session
    
    def test_system_state(self, auth_session):
        """Test /api/system/state endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/system/state")
        assert response.status_code == 200, f"System state failed: {response.text}"
        data = response.json()
        assert "status" in data
        assert "lifecycle" in data
        assert "mode" in data
        print(f"System state: {data.get('status')}, {data.get('lifecycle')}, {data.get('mode')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
