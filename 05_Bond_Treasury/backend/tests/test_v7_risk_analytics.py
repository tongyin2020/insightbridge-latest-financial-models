"""
Test V7 Features: Risk Analytics and AI Brief
Tests for:
- GET /api/risk-analytics - Portfolio risk analytics
- GET /api/ai-brief - AI-generated market brief
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://rate-trading-auto.preview.emergentagent.com')


class TestRiskAnalyticsAPI:
    """Risk Analytics endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session cookies"""
        self.session = requests.Session()
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@trading.com", "password": "Admin@123456"}
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.user = login_response.json()
    
    def test_risk_analytics_returns_200(self):
        """Test risk analytics endpoint returns 200"""
        response = self.session.get(f"{BASE_URL}/api/risk-analytics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("SUCCESS: /api/risk-analytics returns 200")
    
    def test_risk_analytics_has_var_section(self):
        """Test risk analytics has VaR section with required fields"""
        response = self.session.get(f"{BASE_URL}/api/risk-analytics")
        data = response.json()
        
        assert "var" in data, "Missing 'var' section"
        var = data["var"]
        
        required_fields = ["historical_95", "historical_99", "parametric_95", "parametric_99", "cvar_95", "method"]
        for field in required_fields:
            assert field in var, f"Missing VaR field: {field}"
        
        # Verify values are numeric
        assert isinstance(var["historical_95"], (int, float)), "historical_95 should be numeric"
        assert isinstance(var["historical_99"], (int, float)), "historical_99 should be numeric"
        assert isinstance(var["cvar_95"], (int, float)), "cvar_95 should be numeric"
        
        print(f"SUCCESS: VaR section complete - 95%: ${var['historical_95']}, 99%: ${var['historical_99']}")
    
    def test_risk_analytics_has_metrics_section(self):
        """Test risk analytics has metrics section with required fields"""
        response = self.session.get(f"{BASE_URL}/api/risk-analytics")
        data = response.json()
        
        assert "metrics" in data, "Missing 'metrics' section"
        metrics = data["metrics"]
        
        required_fields = ["sharpe_ratio", "sortino_ratio", "max_drawdown_pct", "annual_volatility", "beta", "total_value"]
        for field in required_fields:
            assert field in metrics, f"Missing metrics field: {field}"
        
        print(f"SUCCESS: Metrics section complete - Sharpe: {metrics['sharpe_ratio']}, Sortino: {metrics['sortino_ratio']}")
    
    def test_risk_analytics_has_stress_tests(self):
        """Test risk analytics has stress tests array"""
        response = self.session.get(f"{BASE_URL}/api/risk-analytics")
        data = response.json()
        
        assert "stress_tests" in data, "Missing 'stress_tests' section"
        stress_tests = data["stress_tests"]
        
        assert isinstance(stress_tests, list), "stress_tests should be a list"
        assert len(stress_tests) > 0, "stress_tests should not be empty"
        
        # Check first stress test has required fields
        test = stress_tests[0]
        required_fields = ["name", "description", "impact_pct", "severity", "impact_value", "portfolio_after"]
        for field in required_fields:
            assert field in test, f"Missing stress test field: {field}"
        
        print(f"SUCCESS: {len(stress_tests)} stress test scenarios found")
    
    def test_risk_analytics_has_concentration(self):
        """Test risk analytics has concentration section"""
        response = self.session.get(f"{BASE_URL}/api/risk-analytics")
        data = response.json()
        
        assert "concentration" in data, "Missing 'concentration' section"
        concentration = data["concentration"]
        
        required_fields = ["hhi", "largest_position_pct", "positions", "rating"]
        for field in required_fields:
            assert field in concentration, f"Missing concentration field: {field}"
        
        print(f"SUCCESS: Concentration section complete - HHI: {concentration['hhi']}, Rating: {concentration['rating']}")
    
    def test_risk_analytics_has_risk_distribution(self):
        """Test risk analytics has risk distribution section"""
        response = self.session.get(f"{BASE_URL}/api/risk-analytics")
        data = response.json()
        
        assert "risk_distribution" in data, "Missing 'risk_distribution' section"
        risk_dist = data["risk_distribution"]
        
        required_fields = ["interest_rate", "credit", "liquidity", "market", "operational"]
        for field in required_fields:
            assert field in risk_dist, f"Missing risk distribution field: {field}"
        
        print(f"SUCCESS: Risk distribution complete - Interest Rate: {risk_dist['interest_rate']}%")
    
    def test_risk_analytics_has_return_distribution(self):
        """Test risk analytics has return distribution with histogram"""
        response = self.session.get(f"{BASE_URL}/api/risk-analytics")
        data = response.json()
        
        assert "return_distribution" in data, "Missing 'return_distribution' section"
        ret_dist = data["return_distribution"]
        
        required_fields = ["mean", "std", "skew", "kurtosis", "histogram"]
        for field in required_fields:
            assert field in ret_dist, f"Missing return distribution field: {field}"
        
        assert isinstance(ret_dist["histogram"], list), "histogram should be a list"
        assert len(ret_dist["histogram"]) > 0, "histogram should not be empty"
        
        print(f"SUCCESS: Return distribution complete - Mean: {ret_dist['mean']}%, Std: {ret_dist['std']}%")


class TestAIBriefAPI:
    """AI Brief endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session cookies"""
        self.session = requests.Session()
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@trading.com", "password": "Admin@123456"}
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.user = login_response.json()
    
    def test_ai_brief_returns_200(self):
        """Test AI brief endpoint returns 200"""
        response = self.session.get(f"{BASE_URL}/api/ai-brief")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("SUCCESS: /api/ai-brief returns 200")
    
    def test_ai_brief_has_required_fields(self):
        """Test AI brief has all required fields"""
        response = self.session.get(f"{BASE_URL}/api/ai-brief")
        data = response.json()
        
        required_fields = ["date", "headline", "body", "market_snapshot", "ai_generated"]
        for field in required_fields:
            assert field in data, f"Missing AI brief field: {field}"
        
        print(f"SUCCESS: AI brief has all required fields")
    
    def test_ai_brief_has_headline_and_body(self):
        """Test AI brief has non-empty headline and body"""
        response = self.session.get(f"{BASE_URL}/api/ai-brief")
        data = response.json()
        
        assert len(data["headline"]) > 0, "Headline should not be empty"
        assert len(data["body"]) > 0, "Body should not be empty"
        
        print(f"SUCCESS: AI brief headline: {data['headline'][:60]}...")
    
    def test_ai_brief_has_market_snapshot(self):
        """Test AI brief has market snapshot with required fields"""
        response = self.session.get(f"{BASE_URL}/api/ai-brief")
        data = response.json()
        
        assert "market_snapshot" in data, "Missing market_snapshot"
        snapshot = data["market_snapshot"]
        
        # Check for expected market snapshot fields
        expected_fields = ["y10", "slope", "vix", "curve_signal"]
        for field in expected_fields:
            assert field in snapshot, f"Missing market snapshot field: {field}"
        
        print(f"SUCCESS: Market snapshot - 10Y: {snapshot['y10']}, VIX: {snapshot['vix']}")
    
    def test_ai_brief_ai_generated_flag(self):
        """Test AI brief has ai_generated boolean flag"""
        response = self.session.get(f"{BASE_URL}/api/ai-brief")
        data = response.json()
        
        assert "ai_generated" in data, "Missing ai_generated flag"
        assert isinstance(data["ai_generated"], bool), "ai_generated should be boolean"
        
        print(f"SUCCESS: AI generated flag: {data['ai_generated']}")


class TestHealthEndpoint:
    """Health endpoint tests"""
    
    def test_health_includes_new_features(self):
        """Test health endpoint includes risk_analytics and ai_brief features"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "features" in data, "Missing features list"
        
        assert "risk_analytics" in data["features"], "risk_analytics not in features"
        assert "ai_brief" in data["features"], "ai_brief not in features"
        
        print(f"SUCCESS: Health endpoint includes risk_analytics and ai_brief features")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
