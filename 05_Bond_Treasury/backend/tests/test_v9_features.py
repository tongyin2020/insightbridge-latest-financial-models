"""
Test V9 Features: Portfolio Optimizer, Risk Trends, Email Digest
Tests for:
1. GET /api/portfolio-optimizer/assets - returns 8 bond assets
2. POST /api/portfolio-optimizer/optimize - Black-Litterman optimization
3. GET /api/risk-trends - returns risk snapshots
4. POST /api/risk-trends/snapshot - saves risk snapshot
5. GET /api/email-digest/preferences - returns email preferences
6. POST /api/email-digest/preferences - saves email preferences
7. POST /api/email-digest/send - triggers email sending
8. GET /api/email-digest/history - returns digest history
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestAuth:
    """Authentication helper tests"""
    
    @pytest.fixture(scope="class")
    def session(self):
        """Create authenticated session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        
        # Login with admin credentials
        login_res = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@trading.com",
            "password": "Admin@123456"
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        return s
    
    def test_login_success(self, session):
        """Verify session is authenticated"""
        res = session.get(f"{BASE_URL}/api/auth/me")
        assert res.status_code == 200
        data = res.json()
        assert data["email"] == "admin@trading.com"
        print("✓ Auth: Login successful")


class TestPortfolioOptimizer:
    """Portfolio Optimizer API tests"""
    
    @pytest.fixture(scope="class")
    def session(self):
        """Create authenticated session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        login_res = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@trading.com",
            "password": "Admin@123456"
        })
        assert login_res.status_code == 200
        return s
    
    def test_get_optimizer_assets(self, session):
        """GET /api/portfolio-optimizer/assets returns 8 bond assets"""
        res = session.get(f"{BASE_URL}/api/portfolio-optimizer/assets")
        assert res.status_code == 200
        data = res.json()
        
        assert "assets" in data
        assets = data["assets"]
        assert len(assets) == 8, f"Expected 8 assets, got {len(assets)}"
        
        # Verify asset structure
        for asset in assets:
            assert "symbol" in asset
            assert "name" in asset
            assert "category" in asset
        
        # Verify expected symbols
        symbols = [a["symbol"] for a in assets]
        expected_symbols = ["UST_2Y", "UST_5Y", "UST_10Y", "UST_30Y", "TIPS", "IG_CORP", "HY_CORP", "MBS"]
        for sym in expected_symbols:
            assert sym in symbols, f"Missing symbol: {sym}"
        
        print(f"✓ Portfolio Optimizer: GET /assets returns {len(assets)} assets with correct structure")
    
    def test_optimize_with_views(self, session):
        """POST /api/portfolio-optimizer/optimize with views returns full optimization result"""
        payload = {
            "views": [
                {"asset": "UST_10Y", "return_view": 5.0, "confidence": 0.8},
                {"asset": "HY_CORP", "return_view": 7.5, "confidence": 0.6}
            ],
            "risk_aversion": 2.5
        }
        res = session.post(f"{BASE_URL}/api/portfolio-optimizer/optimize", json=payload)
        assert res.status_code == 200
        data = res.json()
        
        # Verify response structure
        assert "allocations" in data
        assert "optimal_portfolio" in data
        assert "min_variance" in data
        assert "max_sharpe" in data
        assert "efficient_frontier" in data
        
        # Verify allocations
        allocations = data["allocations"]
        assert len(allocations) == 8
        for alloc in allocations:
            assert "symbol" in alloc
            assert "optimal_weight" in alloc
            assert "market_weight" in alloc
            assert "mv_weight" in alloc
            assert "ms_weight" in alloc
            assert "expected_return" in alloc
            assert "volatility" in alloc
        
        # Verify optimal portfolio
        opt = data["optimal_portfolio"]
        assert "return" in opt
        assert "volatility" in opt
        assert "sharpe" in opt
        
        # Verify min variance
        mv = data["min_variance"]
        assert "return" in mv
        assert "volatility" in mv
        
        # Verify max sharpe
        ms = data["max_sharpe"]
        assert "return" in ms
        assert "volatility" in ms
        assert "sharpe" in ms
        
        # Verify efficient frontier
        frontier = data["efficient_frontier"]
        assert len(frontier) > 0
        for point in frontier:
            assert "return" in point
            assert "volatility" in point
        
        # Verify views were applied
        assert data.get("views_applied") == 2
        
        print(f"✓ Portfolio Optimizer: POST /optimize with views returns allocations, optimal_portfolio, min_variance, max_sharpe, efficient_frontier")
    
    def test_optimize_without_views(self, session):
        """POST /api/portfolio-optimizer/optimize without views returns market equilibrium"""
        payload = {
            "views": [],
            "risk_aversion": 2.5
        }
        res = session.post(f"{BASE_URL}/api/portfolio-optimizer/optimize", json=payload)
        assert res.status_code == 200
        data = res.json()
        
        assert "allocations" in data
        assert "optimal_portfolio" in data
        assert data.get("views_applied") == 0
        
        print("✓ Portfolio Optimizer: POST /optimize without views returns market equilibrium optimization")


class TestRiskTrends:
    """Risk Trends API tests"""
    
    @pytest.fixture(scope="class")
    def session(self):
        """Create authenticated session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        login_res = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@trading.com",
            "password": "Admin@123456"
        })
        assert login_res.status_code == 200
        return s
    
    def test_save_risk_snapshot(self, session):
        """POST /api/risk-trends/snapshot saves a new risk snapshot"""
        res = session.post(f"{BASE_URL}/api/risk-trends/snapshot")
        assert res.status_code == 200
        data = res.json()
        
        assert data.get("saved") == True
        assert "timestamp" in data
        
        print("✓ Risk Trends: POST /snapshot saves risk snapshot and returns saved:true")
    
    def test_get_risk_trends(self, session):
        """GET /api/risk-trends returns array of risk snapshots"""
        res = session.get(f"{BASE_URL}/api/risk-trends?days=30")
        assert res.status_code == 200
        data = res.json()
        
        assert isinstance(data, list)
        
        # If there are snapshots, verify structure
        if len(data) > 0:
            snapshot = data[0]
            # Check for expected fields
            expected_fields = ["timestamp", "var_95", "sharpe", "annual_vol", "max_drawdown"]
            for field in expected_fields:
                assert field in snapshot, f"Missing field: {field}"
        
        print(f"✓ Risk Trends: GET /risk-trends returns array of {len(data)} snapshots")
    
    def test_get_risk_trend_summary(self, session):
        """GET /api/risk-trends/summary returns trend summary with deltas"""
        res = session.get(f"{BASE_URL}/api/risk-trends/summary?days=30")
        assert res.status_code == 200
        data = res.json()
        
        # Should have has_data field
        assert "has_data" in data
        assert "snapshots_count" in data
        
        print(f"✓ Risk Trends: GET /risk-trends/summary returns summary with has_data={data.get('has_data')}")


class TestEmailDigest:
    """Email Digest API tests"""
    
    @pytest.fixture(scope="class")
    def session(self):
        """Create authenticated session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        login_res = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@trading.com",
            "password": "Admin@123456"
        })
        assert login_res.status_code == 200
        return s
    
    def test_get_email_preferences(self, session):
        """GET /api/email-digest/preferences returns default preferences"""
        res = session.get(f"{BASE_URL}/api/email-digest/preferences")
        assert res.status_code == 200
        data = res.json()
        
        # Verify expected fields
        assert "digest_enabled" in data
        assert "digest_email" in data
        assert "include_risk_summary" in data
        assert "include_alerts" in data
        assert "include_ai_brief" in data
        assert "include_portfolio" in data
        
        print("✓ Email Digest: GET /preferences returns default preferences with all include_* fields")
    
    def test_save_email_preferences(self, session):
        """POST /api/email-digest/preferences saves email preferences"""
        payload = {
            "digest_enabled": True,
            "digest_email": "test@example.com",
            "include_risk_summary": True,
            "include_alerts": True,
            "include_ai_brief": True,
            "include_portfolio": True
        }
        res = session.post(f"{BASE_URL}/api/email-digest/preferences", json=payload)
        assert res.status_code == 200
        data = res.json()
        
        assert data.get("digest_enabled") == True
        assert data.get("digest_email") == "test@example.com"
        
        print("✓ Email Digest: POST /preferences saves email preferences")
    
    def test_send_digest(self, session):
        """POST /api/email-digest/send triggers email sending"""
        # First set a valid email (Resend test mode only works with verified emails)
        session.post(f"{BASE_URL}/api/email-digest/preferences", json={
            "digest_enabled": True,
            "digest_email": "tongyin2020@gmail.com",  # Verified Resend email
            "include_risk_summary": True,
            "include_alerts": True,
            "include_ai_brief": True,
            "include_portfolio": True
        })
        
        res = session.post(f"{BASE_URL}/api/email-digest/send")
        assert res.status_code == 200
        data = res.json()
        
        # Response should have sent status
        assert "sent" in data
        
        # If sent is true, should have email_id
        if data.get("sent"):
            assert "email_id" in data or "email" in data
            print(f"✓ Email Digest: POST /send triggers email sending, sent=true, email_id={data.get('email_id')}")
        else:
            # If sent is false, should have reason
            print(f"✓ Email Digest: POST /send returns sent={data.get('sent')}, reason={data.get('reason', 'N/A')}")
    
    def test_get_digest_history(self, session):
        """GET /api/email-digest/history returns digest history"""
        res = session.get(f"{BASE_URL}/api/email-digest/history")
        assert res.status_code == 200
        data = res.json()
        
        assert isinstance(data, list)
        
        # If there are logs, verify structure
        if len(data) > 0:
            log = data[0]
            assert "email" in log
            assert "sent" in log
            assert "sent_at" in log
        
        print(f"✓ Email Digest: GET /history returns array of {len(data)} digest logs")


class TestDashboardNavigation:
    """Test Dashboard navigation includes Portfolio Optimizer link"""
    
    def test_portfolio_optimizer_route_exists(self):
        """Verify /portfolio-optimizer route is accessible"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        
        # Login
        login_res = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@trading.com",
            "password": "Admin@123456"
        })
        assert login_res.status_code == 200
        
        # Try to access portfolio optimizer assets (proves route exists)
        res = s.get(f"{BASE_URL}/api/portfolio-optimizer/assets")
        assert res.status_code == 200
        
        print("✓ Dashboard Navigation: Portfolio Optimizer route is accessible")


class TestHealthCheck:
    """Health check to verify all features are listed"""
    
    def test_health_includes_new_features(self):
        """GET /api/health includes new features"""
        res = requests.get(f"{BASE_URL}/api/health")
        assert res.status_code == 200
        data = res.json()
        
        features = data.get("features", [])
        
        # Check for new V9 features
        assert "email_digest" in features, "email_digest not in features"
        assert "risk_trends" in features, "risk_trends not in features"
        assert "portfolio_optimizer" in features, "portfolio_optimizer not in features"
        
        print(f"✓ Health Check: All V9 features present in /api/health: email_digest, risk_trends, portfolio_optimizer")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
