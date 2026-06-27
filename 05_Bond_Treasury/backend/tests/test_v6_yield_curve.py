"""
Test V6 Features: Yield Curve Analytics, Bond Auctions, Real Historical Backtesting
Tests for iteration 6 - P2 (real historical backtesting), P3 (yield curve visualization), bond auction notifications
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://rate-trading-auto.preview.emergentagent.com')


class TestYieldCurveAPI:
    """Tests for Yield Curve endpoints"""
    
    def test_yield_curve_current(self):
        """Test GET /api/yield-curve/current returns curve data with shape analysis"""
        response = requests.get(f"{BASE_URL}/api/yield-curve/current")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # Verify curve data structure
        assert "curve" in data, "Response should contain 'curve'"
        assert "shape" in data, "Response should contain 'shape'"
        assert "timestamp" in data, "Response should contain 'timestamp'"
        
        # Verify 5 tenors present
        curve = data["curve"]
        expected_tenors = ["3M", "2Y", "5Y", "10Y", "30Y"]
        for tenor in expected_tenors:
            assert tenor in curve, f"Tenor {tenor} should be in curve"
            assert "yield" in curve[tenor], f"Tenor {tenor} should have 'yield'"
            assert "change_1d" in curve[tenor], f"Tenor {tenor} should have 'change_1d'"
        
        # Verify shape analysis
        shape = data["shape"]
        assert "type" in shape, "Shape should have 'type'"
        assert shape["type"] in ["NORMAL", "FLAT", "INVERTED", "HUMPED", "UNKNOWN"], f"Invalid shape type: {shape['type']}"
        assert "risk_level" in shape, "Shape should have 'risk_level'"
        assert "slope_10y_3m" in shape, "Shape should have 'slope_10y_3m'"
        assert "steepness" in shape, "Shape should have 'steepness'"
        assert "description" in shape, "Shape should have 'description'"
        
        print(f"✓ Yield curve current: shape={shape['type']}, slope_10y_3m={shape['slope_10y_3m']}")
    
    def test_yield_curve_historical(self):
        """Test GET /api/yield-curve/historical returns array of historical data points"""
        response = requests.get(f"{BASE_URL}/api/yield-curve/historical?period=3mo")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        assert len(data) > 0, "Historical data should not be empty"
        
        # Verify data structure
        first_entry = data[0]
        assert "date" in first_entry, "Entry should have 'date'"
        assert "10Y" in first_entry, "Entry should have '10Y' yield"
        assert "slope" in first_entry, "Entry should have 'slope'"
        
        print(f"✓ Yield curve historical: {len(data)} data points, first date={first_entry['date']}")
    
    def test_yield_curve_historical_periods(self):
        """Test historical API with different periods"""
        periods = ["1mo", "3mo", "6mo", "1y"]
        for period in periods:
            response = requests.get(f"{BASE_URL}/api/yield-curve/historical?period={period}")
            assert response.status_code == 200, f"Period {period}: Expected 200, got {response.status_code}"
            data = response.json()
            assert isinstance(data, list), f"Period {period}: Response should be a list"
            print(f"✓ Historical period {period}: {len(data)} data points")
    
    def test_yield_curve_heatmap(self):
        """Test GET /api/yield-curve/heatmap returns daily yield changes"""
        response = requests.get(f"{BASE_URL}/api/yield-curve/heatmap?period=3mo")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        if len(data) > 0:
            first_entry = data[0]
            assert "date" in first_entry, "Entry should have 'date'"
            # Check for change fields
            change_fields = ["3M_change", "5Y_change", "10Y_change", "30Y_change"]
            for field in change_fields:
                assert field in first_entry, f"Entry should have '{field}'"
        
        print(f"✓ Yield curve heatmap: {len(data)} data points")


class TestBondAuctionAPI:
    """Tests for Bond Auction endpoints"""
    
    def test_auctions_upcoming(self):
        """Test GET /api/auctions/upcoming returns array of upcoming auction entries"""
        response = requests.get(f"{BASE_URL}/api/auctions/upcoming")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        assert len(data) > 0, "Should have upcoming auctions"
        
        # Verify auction structure
        first_auction = data[0]
        required_fields = ["tenor", "auction_date", "days_away", "frequency", "estimated_size_bn", "status", "impact_level"]
        for field in required_fields:
            assert field in first_auction, f"Auction should have '{field}'"
        
        # Verify impact levels
        valid_impacts = ["HIGH", "MEDIUM", "LOW"]
        for auction in data[:5]:
            assert auction["impact_level"] in valid_impacts, f"Invalid impact level: {auction['impact_level']}"
        
        print(f"✓ Upcoming auctions: {len(data)} auctions, first={first_auction['tenor']} on {first_auction['auction_date']}")
    
    def test_auctions_results(self):
        """Test GET /api/auctions/results returns recent auction results"""
        response = requests.get(f"{BASE_URL}/api/auctions/results?limit=10")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        if len(data) > 0:
            first_result = data[0]
            required_fields = ["tenor", "auction_date", "high_yield", "bid_to_cover", "demand_rating"]
            for field in required_fields:
                assert field in first_result, f"Result should have '{field}'"
            
            # Verify demand ratings
            valid_ratings = ["STRONG", "AVERAGE", "WEAK"]
            assert first_result["demand_rating"] in valid_ratings, f"Invalid demand rating: {first_result['demand_rating']}"
        
        print(f"✓ Auction results: {len(data)} results")
    
    def test_auctions_calendar(self):
        """Test GET /api/auctions/calendar returns calendar summary"""
        response = requests.get(f"{BASE_URL}/api/auctions/calendar")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify calendar summary structure
        assert "this_week" in data, "Calendar should have 'this_week'"
        assert "next_week" in data, "Calendar should have 'next_week'"
        assert "total_supply_this_week_bn" in data, "Calendar should have 'total_supply_this_week_bn'"
        assert "auction_count_this_week" in data, "Calendar should have 'auction_count_this_week'"
        assert "next_major_auction" in data, "Calendar should have 'next_major_auction'"
        
        # Verify this_week is a list
        assert isinstance(data["this_week"], list), "'this_week' should be a list"
        assert isinstance(data["next_week"], list), "'next_week' should be a list"
        
        print(f"✓ Auction calendar: {data['auction_count_this_week']} auctions this week, ${data['total_supply_this_week_bn']}B supply")


class TestBacktestRealData:
    """Tests for Backtest with real historical data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session"""
        self.session = requests.Session()
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@trading.com", "password": "Admin@123456"}
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
    
    def test_backtest_ai_hybrid_real_data(self):
        """Test POST /api/backtest/run with AI_HYBRID strategy returns trades with real WTI/bond data"""
        response = self.session.post(
            f"{BASE_URL}/api/backtest/run",
            json={
                "strategy_type": "AI_HYBRID",
                "start_date": "2025-10-01",
                "end_date": "2025-12-31",
                "initial_capital": 100000,
                "strategy_params": {
                    "ispread_upper": 15.0,
                    "ispread_lower": 10.0,
                    "stop_loss_pct": 0.05,
                    "take_profit_pct": 0.10
                }
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify backtest result structure
        assert data["strategy"] == "AI_HYBRID", "Strategy should be AI_HYBRID"
        assert "equity_curve" in data, "Result should have 'equity_curve'"
        assert "trades" in data, "Result should have 'trades'"
        assert "total_return" in data, "Result should have 'total_return'"
        assert "sharpe_ratio" in data, "Result should have 'sharpe_ratio'"
        
        # Verify equity_curve entries have real data fields
        equity_curve = data["equity_curve"]
        assert len(equity_curve) > 0, "Equity curve should not be empty"
        
        first_entry = equity_curve[0]
        assert "wti" in first_entry, "Equity curve entry should have 'wti' field"
        assert "bond_yield" in first_entry, "Equity curve entry should have 'bond_yield' field"
        assert "ispread" in first_entry, "Equity curve entry should have 'ispread' field"
        
        # Verify WTI and bond_yield are realistic values
        assert 50 < first_entry["wti"] < 150, f"WTI price should be realistic: {first_entry['wti']}"
        assert 0 < first_entry["bond_yield"] < 10, f"Bond yield should be realistic: {first_entry['bond_yield']}"
        
        print(f"✓ Backtest AI_HYBRID: {data['total_trades']} trades, return={data['total_return_pct']}%, sharpe={data['sharpe_ratio']}")
        print(f"  First equity entry: wti={first_entry['wti']}, bond_yield={first_entry['bond_yield']}, ispread={first_entry['ispread']}")
    
    def test_backtest_mean_reversion(self):
        """Test backtest with MEAN_REVERSION strategy"""
        response = self.session.post(
            f"{BASE_URL}/api/backtest/run",
            json={
                "strategy_type": "MEAN_REVERSION",
                "start_date": "2025-09-01",
                "end_date": "2025-12-31",
                "initial_capital": 50000,
                "strategy_params": {}
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["strategy"] == "MEAN_REVERSION"
        assert len(data["equity_curve"]) > 0
        
        print(f"✓ Backtest MEAN_REVERSION: {data['total_trades']} trades, return={data['total_return_pct']}%")
    
    def test_backtest_momentum(self):
        """Test backtest with MOMENTUM strategy"""
        response = self.session.post(
            f"{BASE_URL}/api/backtest/run",
            json={
                "strategy_type": "MOMENTUM",
                "start_date": "2025-09-01",
                "end_date": "2025-12-31",
                "initial_capital": 50000,
                "strategy_params": {}
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["strategy"] == "MOMENTUM"
        
        print(f"✓ Backtest MOMENTUM: {data['total_trades']} trades, return={data['total_return_pct']}%")
    
    def test_backtest_spread_arbitrage(self):
        """Test backtest with SPREAD_ARBITRAGE strategy"""
        response = self.session.post(
            f"{BASE_URL}/api/backtest/run",
            json={
                "strategy_type": "SPREAD_ARBITRAGE",
                "start_date": "2025-09-01",
                "end_date": "2025-12-31",
                "initial_capital": 50000,
                "strategy_params": {}
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["strategy"] == "SPREAD_ARBITRAGE"
        
        print(f"✓ Backtest SPREAD_ARBITRAGE: {data['total_trades']} trades, return={data['total_return_pct']}%")


class TestHealthAndFeatures:
    """Test health endpoint includes new features"""
    
    def test_health_includes_yield_curve_features(self):
        """Test health endpoint lists yield_curve and bond_auctions features"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "features" in data, "Health should have 'features'"
        
        features = data["features"]
        assert "yield_curve" in features, "Features should include 'yield_curve'"
        assert "bond_auctions" in features, "Features should include 'bond_auctions'"
        
        print(f"✓ Health check: features include yield_curve and bond_auctions")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
