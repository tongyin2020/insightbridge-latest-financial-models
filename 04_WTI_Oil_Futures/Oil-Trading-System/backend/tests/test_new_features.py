"""
Test suite for NEW features in iteration 5:
1. Calendar Spread options strategy
2. Ratio Spread options strategy
3. AI Auto Strategy Selector
4. Push Notifications (MongoDB persistence)
5. Tradovate broker API integration (simulation mode)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://petro-trading-ai.preview.emergentagent.com').rstrip('/')


class TestCalendarSpread:
    """Calendar Spread options strategy tests"""
    
    def test_create_calendar_spread_call(self):
        """Test creating a call calendar spread"""
        response = requests.post(
            f"{BASE_URL}/api/options/strategy/calendar-spread",
            params={
                "symbol": "CL",
                "option_type": "call",
                "near_expiry_days": 30,
                "far_expiry_days": 60
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert data["type"] == "calendar_spread"
        assert data["option_type"] == "call"
        assert "legs" in data
        assert len(data["legs"]) == 2
        
        # Verify legs have different expiries
        assert data["legs"][0]["quantity"] == -1  # Short near-term
        assert data["legs"][1]["quantity"] == 1   # Long far-term
        
        # Verify Greeks
        assert "greeks" in data
        assert "delta" in data["greeks"]
        assert "theta" in data["greeks"]
        assert "vega" in data["greeks"]
        
        # Verify risk metrics
        assert "max_profit" in data
        assert "max_loss" in data
        assert "breakeven_points" in data
        
    def test_create_calendar_spread_put(self):
        """Test creating a put calendar spread"""
        response = requests.post(
            f"{BASE_URL}/api/options/strategy/calendar-spread",
            params={
                "symbol": "CL",
                "option_type": "put",
                "near_expiry_days": 30,
                "far_expiry_days": 60
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["option_type"] == "put"
        assert data["type"] == "calendar_spread"
        
    def test_calendar_spread_invalid_symbol(self):
        """Test calendar spread with invalid symbol"""
        response = requests.post(
            f"{BASE_URL}/api/options/strategy/calendar-spread",
            params={
                "symbol": "INVALID",
                "option_type": "call"
            }
        )
        assert response.status_code == 404


class TestRatioSpread:
    """Ratio Spread options strategy tests"""
    
    def test_create_ratio_spread_call(self):
        """Test creating a call ratio spread (1x2)"""
        response = requests.post(
            f"{BASE_URL}/api/options/strategy/ratio-spread",
            params={
                "symbol": "CL",
                "option_type": "call",
                "ratio": 2,
                "expiry_days": 30
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert data["type"] == "ratio_spread"
        assert data["option_type"] == "call"
        assert data["ratio"] == "1x2"
        assert "legs" in data
        assert len(data["legs"]) == 2
        
        # Verify leg quantities
        assert data["legs"][0]["quantity"] == 1   # Long 1
        assert data["legs"][1]["quantity"] == -2  # Short 2
        
        # Verify Greeks
        assert "greeks" in data
        
    def test_create_ratio_spread_put(self):
        """Test creating a put ratio spread"""
        response = requests.post(
            f"{BASE_URL}/api/options/strategy/ratio-spread",
            params={
                "symbol": "CL",
                "option_type": "put",
                "ratio": 2,
                "expiry_days": 30
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["option_type"] == "put"
        
    def test_ratio_spread_custom_ratio(self):
        """Test ratio spread with custom ratio (1x3)"""
        response = requests.post(
            f"{BASE_URL}/api/options/strategy/ratio-spread",
            params={
                "symbol": "CL",
                "option_type": "call",
                "ratio": 3,
                "expiry_days": 30
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ratio"] == "1x3"
        assert data["legs"][1]["quantity"] == -3


class TestAutoStrategySelector:
    """AI Auto Strategy Selector tests"""
    
    def test_get_auto_strategy_recommendation(self):
        """Test getting AI strategy recommendation"""
        response = requests.get(f"{BASE_URL}/api/options/auto-strategy/CL")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "recommended_strategy" in data
        assert "confidence" in data
        assert "direction_bias" in data
        assert "reasoning" in data
        assert "risk_level" in data
        assert "key_factors" in data
        
        # Verify valid strategy type
        valid_strategies = ["straddle", "strangle", "iron_condor", "butterfly", "calendar_spread", "ratio_spread"]
        assert data["recommended_strategy"] in valid_strategies
        
        # Verify confidence is between 0 and 1
        assert 0 <= data["confidence"] <= 1
        
        # Verify direction bias
        assert data["direction_bias"] in ["bullish", "bearish", "neutral"]
        
        # Verify risk level
        assert data["risk_level"] in ["low", "medium", "high"]
        
        # Verify source (rules or ai)
        assert data.get("source") in ["rules", "ai"]
        
    def test_auto_strategy_different_symbols(self):
        """Test auto strategy for different symbols"""
        for symbol in ["CL", "BZ", "NG"]:
            response = requests.get(f"{BASE_URL}/api/options/auto-strategy/{symbol}")
            assert response.status_code == 200
            data = response.json()
            assert "recommended_strategy" in data
            
    def test_auto_strategy_invalid_symbol(self):
        """Test auto strategy with invalid symbol"""
        response = requests.get(f"{BASE_URL}/api/options/auto-strategy/INVALID")
        assert response.status_code == 404


class TestNotifications:
    """Push Notifications tests"""
    
    def test_get_notifications(self):
        """Test getting notifications list"""
        response = requests.get(f"{BASE_URL}/api/notifications")
        assert response.status_code == 200
        data = response.json()
        
        assert "notifications" in data
        assert "unread_count" in data
        assert isinstance(data["notifications"], list)
        assert isinstance(data["unread_count"], int)
        
    def test_send_test_notification(self):
        """Test sending a test notification"""
        response = requests.post(f"{BASE_URL}/api/notifications/test")
        assert response.status_code == 200
        data = response.json()
        
        # Verify notification structure
        assert "id" in data
        assert "type" in data
        assert "title" in data
        assert "message" in data
        assert "severity" in data
        assert "timestamp" in data
        assert "read" in data
        
        # Verify values
        assert data["type"] == "system"
        assert data["title"] == "Test Notification"
        assert data["read"] == False
        
    def test_mark_all_notifications_read(self):
        """Test marking all notifications as read"""
        # First send a test notification
        requests.post(f"{BASE_URL}/api/notifications/test")
        
        # Mark all as read
        response = requests.post(f"{BASE_URL}/api/notifications/read-all")
        assert response.status_code == 200
        data = response.json()
        assert "marked_read" in data
        
    def test_mark_single_notification_read(self):
        """Test marking a single notification as read"""
        # First send a test notification
        notif_response = requests.post(f"{BASE_URL}/api/notifications/test")
        notif_id = notif_response.json()["id"]
        
        # Mark as read
        response = requests.post(f"{BASE_URL}/api/notifications/{notif_id}/read")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        
    def test_get_notifications_unread_only(self):
        """Test getting only unread notifications"""
        response = requests.get(f"{BASE_URL}/api/notifications?unread_only=true")
        assert response.status_code == 200
        data = response.json()
        assert "notifications" in data


class TestTradovateIntegration:
    """Tradovate broker API integration tests (simulation mode)"""
    
    def test_get_tradovate_status(self):
        """Test getting Tradovate connection status"""
        response = requests.get(f"{BASE_URL}/api/tradovate/status")
        assert response.status_code == 200
        data = response.json()
        
        # Verify status fields
        assert "is_configured" in data
        assert "is_demo" in data
        assert "connected" in data
        
        # In simulation mode, should not be configured
        assert data["is_demo"] == True
        # Without API keys, should not be connected
        assert data["connected"] == False


class TestOptionsBacktestNewStrategies:
    """Options backtest tests for new strategies"""
    
    def test_backtest_calendar_spread(self):
        """Test backtesting calendar spread strategy"""
        response = requests.post(
            f"{BASE_URL}/api/options/backtest",
            params={
                "strategy_type": "calendar_spread",
                "symbol": "CL",
                "num_simulations": 30
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify backtest results
        assert data["strategy_type"] == "calendar_spread"
        assert data["symbol"] == "CL"
        assert "num_trades" in data
        assert "win_rate" in data
        assert "total_pnl" in data
        assert "avg_pnl_per_trade" in data
        assert "best_conditions" in data
        assert "sample_trades" in data
        
    def test_backtest_ratio_spread(self):
        """Test backtesting ratio spread strategy"""
        response = requests.post(
            f"{BASE_URL}/api/options/backtest",
            params={
                "strategy_type": "ratio_spread",
                "symbol": "CL",
                "num_simulations": 30
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["strategy_type"] == "ratio_spread"
        assert "win_rate" in data
        assert "best_conditions" in data


class TestExistingEndpointsStillWork:
    """Verify existing endpoints still work after new features"""
    
    def test_system_status(self):
        """Test system status endpoint"""
        response = requests.get(f"{BASE_URL}/api/system/status")
        assert response.status_code == 200
        data = response.json()
        assert "current_symbol" in data
        assert "current_regime" in data
        assert "equity" in data
        
    def test_option_chain(self):
        """Test option chain endpoint"""
        response = requests.get(f"{BASE_URL}/api/options/chain/CL")
        assert response.status_code == 200
        data = response.json()
        assert "options" in data
        assert len(data["options"]) > 0
        
    def test_straddle_strategy(self):
        """Test straddle strategy still works"""
        response = requests.post(f"{BASE_URL}/api/options/strategy/straddle?symbol=CL")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "straddle"
        
    def test_iron_condor_strategy(self):
        """Test iron condor strategy still works"""
        response = requests.post(f"{BASE_URL}/api/options/strategy/iron-condor?symbol=CL")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "iron_condor"
        
    def test_volatility_analysis(self):
        """Test volatility analysis endpoint"""
        response = requests.get(f"{BASE_URL}/api/options/volatility/CL")
        assert response.status_code == 200
        data = response.json()
        assert "recommendation" in data
        assert "current_iv" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
