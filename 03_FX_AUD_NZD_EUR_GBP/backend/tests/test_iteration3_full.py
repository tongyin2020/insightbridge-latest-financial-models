"""
Iteration 3 - Full Backend API Tests
Testing: Telegram REAL delivery, MongoDB persistence, Core APIs, Backtest data
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://aud-nzd-signals.preview.emergentagent.com').rstrip('/')

# Telegram credentials from test_credentials.md
TELEGRAM_BOT_TOKEN = "your_telegram_bot_token_here"
TELEGRAM_CHAT_ID = "8670001641"


class TestHealthAndCoreAPIs:
    """Test core API endpoints"""
    
    def test_health_endpoint(self):
        """Health endpoint returns valid data"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "telegram_configured" in data
        assert "ai_configured" in data
        assert "pairs" in data
        assert "AUD/USD" in data["pairs"]
        assert "NZD/USD" in data["pairs"]
        print(f"Health check passed: telegram_configured={data['telegram_configured']}")
    
    def test_prices_aud_usd(self):
        """AUD/USD price endpoint returns valid data"""
        response = requests.get(f"{BASE_URL}/api/prices/AUD_USD")
        assert response.status_code == 200
        data = response.json()
        assert "pair" in data
        assert data["pair"] == "AUD/USD"
        # Price data is nested under 'price' key
        price = data.get("price", data)
        assert "mid" in price
        assert "bid" in price
        assert "ask" in price
        assert "spread_pips" in price
        print(f"AUD/USD price: {price['mid']}, spread: {price['spread_pips']} pips")
    
    def test_prices_nzd_usd(self):
        """NZD/USD price endpoint returns valid data"""
        response = requests.get(f"{BASE_URL}/api/prices/NZD_USD")
        assert response.status_code == 200
        data = response.json()
        assert data["pair"] == "NZD/USD"
        price = data.get("price", data)
        assert "mid" in price
        print(f"NZD/USD price: {price['mid']}")
    
    def test_signals_current(self):
        """Current signals endpoint returns valid data"""
        response = requests.get(f"{BASE_URL}/api/signals/current")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        # Should have signals for both pairs
        print(f"Signals: {list(data.keys())}")
    
    def test_events_list(self):
        """Events endpoint returns economic calendar"""
        response = requests.get(f"{BASE_URL}/api/events")
        assert response.status_code == 200
        data = response.json()
        # Events may be wrapped in an object with 'events' key
        events = data.get("events", data) if isinstance(data, dict) else data
        assert isinstance(events, list)
        if len(events) > 0:
            event = events[0]
            assert "title" in event
            assert "impact" in event
            assert "datetime" in event
        print(f"Events count: {len(events)}")
    
    def test_risk_status(self):
        """Risk status endpoint returns valid data"""
        response = requests.get(f"{BASE_URL}/api/risk/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "can_trade" in data
        assert "risk_level" in data
        assert "daily_stats" in data
        print(f"Risk status: {data['status']}, can_trade: {data['can_trade']}")


class TestTelegramRealDelivery:
    """Test Telegram REAL message delivery - LIMIT TO 2-3 MESSAGES"""
    
    def test_telegram_status_configured(self):
        """Telegram status shows configured"""
        response = requests.get(f"{BASE_URL}/api/telegram/status")
        assert response.status_code == 200
        data = response.json()
        assert "configured" in data
        assert "bot_token_set" in data
        assert "chat_id_set" in data
        # Should be configured since bot token is in .env
        print(f"Telegram configured: {data['configured']}, token_set: {data['bot_token_set']}, chat_id_set: {data['chat_id_set']}")
    
    def test_telegram_test_real_delivery(self):
        """POST /api/telegram/test sends REAL message to Telegram"""
        response = requests.post(
            f"{BASE_URL}/api/telegram/test",
            json={"message": "Iteration 3 Test - Real Telegram delivery working!"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        # Should return success:true if Telegram is properly configured
        print(f"Telegram test result: success={data.get('success')}, message={data.get('message', '')}")
        # This is the key assertion - real delivery should succeed
        assert data["success"] == True, f"Telegram delivery failed: {data}"
    
    def test_telegram_send_signal_alert(self):
        """POST /api/telegram/send-signal-alert sends formatted signal"""
        response = requests.post(
            f"{BASE_URL}/api/telegram/send-signal-alert",
            params={
                "pair": "AUD/USD",
                "direction": "BUY",
                "confidence": 75.5,
                "reason": "Test signal from iteration 3"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        print(f"Signal alert result: success={data.get('success')}")
        # Real delivery should succeed
        assert data["success"] == True, f"Signal alert failed: {data}"


class TestTelegramConfigPersistence:
    """Test Telegram config persistence to MongoDB"""
    
    def test_telegram_config_save_and_retrieve(self):
        """POST /api/telegram/config saves to MongoDB, GET /api/telegram/status reflects it"""
        # First, save config
        response = requests.post(
            f"{BASE_URL}/api/telegram/config",
            json={
                "bot_token": TELEGRAM_BOT_TOKEN,
                "chat_id": TELEGRAM_CHAT_ID
            }
        )
        assert response.status_code == 200
        save_data = response.json()
        assert save_data["configured"] == True
        assert save_data["bot_token_set"] == True
        assert save_data["chat_id_set"] == True
        print(f"Config saved: {save_data}")
        
        # Then verify via status endpoint
        status_response = requests.get(f"{BASE_URL}/api/telegram/status")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["configured"] == True
        assert status_data["bot_token_set"] == True
        assert status_data["chat_id_set"] == True
        print(f"Config verified via status: {status_data}")


class TestTelegramHistory:
    """Test Telegram alert history from MongoDB"""
    
    def test_telegram_history_returns_alerts(self):
        """GET /api/telegram/history returns alerts stored in MongoDB"""
        response = requests.get(f"{BASE_URL}/api/telegram/history")
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        alerts = data["alerts"]
        assert isinstance(alerts, list)
        print(f"Alert history count: {len(alerts)}")
        
        # If there are alerts, verify structure
        if len(alerts) > 0:
            alert = alerts[0]
            assert "type" in alert
            assert "timestamp" in alert
            print(f"Latest alert: type={alert['type']}, timestamp={alert['timestamp']}")


class TestMongoDBSettingsPersistence:
    """Test settings persistence to MongoDB"""
    
    def test_kill_switch_persistence(self):
        """PUT /api/settings/kill_switch persists to MongoDB"""
        # Set kill_switch to true
        response = requests.put(
            f"{BASE_URL}/api/settings/kill_switch",
            json={"value": "true"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "kill_switch"
        assert data["value"] == "true"
        print(f"Kill switch set to true: {data}")
        
        # Verify via settings endpoint
        settings_response = requests.get(f"{BASE_URL}/api/settings")
        assert settings_response.status_code == 200
        settings = settings_response.json()
        assert settings["kill_switch"] == "true"
        print(f"Kill switch verified: {settings['kill_switch']}")
        
        # Reset kill_switch to false
        reset_response = requests.put(
            f"{BASE_URL}/api/settings/kill_switch",
            json={"value": "false"}
        )
        assert reset_response.status_code == 200
        print("Kill switch reset to false")


class TestBacktestData:
    """Test backtest data from MongoDB"""
    
    def test_backtest_stats_returns_50_trades(self):
        """GET /api/backtest/stats returns 50 trades"""
        response = requests.get(f"{BASE_URL}/api/backtest/stats")
        assert response.status_code == 200
        data = response.json()
        
        assert "summary" in data
        summary = data["summary"]
        assert "total_trades" in summary
        
        # Should have 50 seeded trades
        total_trades = summary["total_trades"]
        print(f"Backtest total trades: {total_trades}")
        assert total_trades == 50, f"Expected 50 trades, got {total_trades}"
        
        # Verify other summary fields
        assert "overall_success_rate" in summary
        assert "total_pnl_pips" in summary
        print(f"Success rate: {summary['overall_success_rate']}%, Total PnL: {summary['total_pnl_pips']} pips")
    
    def test_backtest_results_list(self):
        """GET /api/backtest/results returns trade list"""
        response = requests.get(f"{BASE_URL}/api/backtest/results")
        assert response.status_code == 200
        data = response.json()
        
        assert "results" in data
        results = data["results"]
        assert isinstance(results, list)
        assert len(results) == 50, f"Expected 50 results, got {len(results)}"
        
        # Verify result structure
        if len(results) > 0:
            result = results[0]
            assert "pair" in result
            assert "event_title" in result
            assert "pnl_pips" in result
            print(f"Sample result: pair={result['pair']}, event={result['event_title']}, pnl={result['pnl_pips']}")
    
    def test_backtest_chart_data(self):
        """GET /api/backtest/chart-data returns chart data"""
        response = requests.get(f"{BASE_URL}/api/backtest/chart-data")
        assert response.status_code == 200
        data = response.json()
        
        assert "chart_data" in data
        chart_data = data["chart_data"]
        assert isinstance(chart_data, list)
        print(f"Chart data points: {len(chart_data)}")


class TestRiskControlAPIs:
    """Test risk control system APIs"""
    
    def test_risk_capital_protection(self):
        """Risk capital protection endpoint returns valid data"""
        response = requests.get(f"{BASE_URL}/api/risk/capital-protection")
        assert response.status_code == 200
        data = response.json()
        assert "daily_pnl" in data
        assert "daily_limit" in data
        assert "capital_safety_score" in data
        print(f"Capital protection: daily_pnl={data['daily_pnl']}, safety_score={data['capital_safety_score']}")
    
    def test_risk_config(self):
        """Risk config endpoint returns valid data"""
        response = requests.get(f"{BASE_URL}/api/risk/config")
        assert response.status_code == 200
        data = response.json()
        assert "stop_loss_levels" in data
        assert "daily_limits" in data
        print(f"Risk config: stop_loss_levels={data['stop_loss_levels']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
