"""
Telegram API Tests for FX Trading System
Tests Telegram configuration, status, test message, and history endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://aud-nzd-signals.preview.emergentagent.com').rstrip('/')


class TestTelegramStatus:
    """Test GET /api/telegram/status endpoint"""
    
    def test_telegram_status_returns_200(self):
        """Test that telegram status endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/telegram/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ Telegram status endpoint returns 200")
    
    def test_telegram_status_response_structure(self):
        """Test that telegram status has correct response structure"""
        response = requests.get(f"{BASE_URL}/api/telegram/status")
        data = response.json()
        
        # Check required fields
        assert "configured" in data, "Missing 'configured' field"
        assert "bot_token_set" in data, "Missing 'bot_token_set' field"
        assert "chat_id_set" in data, "Missing 'chat_id_set' field"
        assert "daily_alerts_sent" in data, "Missing 'daily_alerts_sent' field"
        
        # Check types
        assert isinstance(data["configured"], bool), "'configured' should be boolean"
        assert isinstance(data["bot_token_set"], bool), "'bot_token_set' should be boolean"
        assert isinstance(data["chat_id_set"], bool), "'chat_id_set' should be boolean"
        assert isinstance(data["daily_alerts_sent"], int), "'daily_alerts_sent' should be integer"
        
        print(f"✓ Telegram status response structure valid: configured={data['configured']}, bot_token_set={data['bot_token_set']}, chat_id_set={data['chat_id_set']}")


class TestTelegramConfig:
    """Test POST /api/telegram/config endpoint"""
    
    def test_telegram_config_save_returns_200(self):
        """Test that saving telegram config returns 200"""
        payload = {
            "bot_token": "test_token_123",
            "chat_id": "test_chat_456"
        }
        response = requests.post(
            f"{BASE_URL}/api/telegram/config",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ Telegram config save returns 200")
    
    def test_telegram_config_response_structure(self):
        """Test that telegram config response has correct structure"""
        payload = {
            "bot_token": "test_token_abc",
            "chat_id": "test_chat_xyz"
        }
        response = requests.post(
            f"{BASE_URL}/api/telegram/config",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        data = response.json()
        
        # Check required fields
        assert "success" in data, "Missing 'success' field"
        assert "configured" in data, "Missing 'configured' field"
        assert "bot_token_set" in data, "Missing 'bot_token_set' field"
        assert "chat_id_set" in data, "Missing 'chat_id_set' field"
        
        # After setting both, configured should be True
        assert data["success"] == True, "'success' should be True"
        assert data["bot_token_set"] == True, "'bot_token_set' should be True after setting"
        assert data["chat_id_set"] == True, "'chat_id_set' should be True after setting"
        assert data["configured"] == True, "'configured' should be True when both are set"
        
        print(f"✓ Telegram config response valid: success={data['success']}, configured={data['configured']}")
    
    def test_telegram_config_partial_update(self):
        """Test that partial config update works (only bot_token)"""
        payload = {"bot_token": "partial_token_only"}
        response = requests.post(
            f"{BASE_URL}/api/telegram/config",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["bot_token_set"] == True
        print("✓ Telegram partial config update works")
    
    def test_telegram_config_verify_persistence(self):
        """Test that config is persisted by checking status after save"""
        # Save config
        payload = {
            "bot_token": "persist_test_token",
            "chat_id": "persist_test_chat"
        }
        save_response = requests.post(
            f"{BASE_URL}/api/telegram/config",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert save_response.status_code == 200
        
        # Verify via status endpoint
        status_response = requests.get(f"{BASE_URL}/api/telegram/status")
        status_data = status_response.json()
        
        assert status_data["bot_token_set"] == True, "bot_token should be set after save"
        assert status_data["chat_id_set"] == True, "chat_id should be set after save"
        assert status_data["configured"] == True, "configured should be True after save"
        
        print("✓ Telegram config persistence verified via status endpoint")


class TestTelegramTestMessage:
    """Test POST /api/telegram/test endpoint"""
    
    def test_telegram_test_message_returns_200(self):
        """Test that sending test message returns 200"""
        payload = {"message": "Test message from pytest"}
        response = requests.post(
            f"{BASE_URL}/api/telegram/test",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ Telegram test message endpoint returns 200")
    
    def test_telegram_test_message_response_structure(self):
        """Test that test message response has correct structure"""
        payload = {"message": "Structure test message"}
        response = requests.post(
            f"{BASE_URL}/api/telegram/test",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        data = response.json()
        
        # Check required fields
        assert "success" in data, "Missing 'success' field"
        assert "message" in data, "Missing 'message' field"
        
        # Since no real Telegram bot is configured, success may be False (fallback mode)
        # But the endpoint should still work
        assert isinstance(data["success"], bool), "'success' should be boolean"
        assert isinstance(data["message"], str), "'message' should be string"
        
        print(f"✓ Telegram test message response valid: success={data['success']}, message={data['message']}")
    
    def test_telegram_test_message_default_message(self):
        """Test that default message works when no message provided"""
        payload = {}  # Empty payload should use default message
        response = requests.post(
            f"{BASE_URL}/api/telegram/test",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        # Should still return 200 even with empty payload (uses default)
        assert response.status_code == 200 or response.status_code == 422, f"Expected 200 or 422, got {response.status_code}"
        print("✓ Telegram test message handles empty payload")


class TestTelegramHistory:
    """Test GET /api/telegram/history endpoint"""
    
    def test_telegram_history_returns_200(self):
        """Test that telegram history endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/telegram/history")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ Telegram history endpoint returns 200")
    
    def test_telegram_history_response_structure(self):
        """Test that telegram history has correct response structure"""
        response = requests.get(f"{BASE_URL}/api/telegram/history")
        data = response.json()
        
        # Check required fields
        assert "alerts" in data, "Missing 'alerts' field"
        assert isinstance(data["alerts"], list), "'alerts' should be a list"
        
        print(f"✓ Telegram history response valid: {len(data['alerts'])} alerts found")
    
    def test_telegram_history_with_limit(self):
        """Test that telegram history respects limit parameter"""
        response = requests.get(f"{BASE_URL}/api/telegram/history?limit=5")
        assert response.status_code == 200
        data = response.json()
        
        # Should have at most 5 alerts
        assert len(data["alerts"]) <= 5, f"Expected at most 5 alerts, got {len(data['alerts'])}"
        print(f"✓ Telegram history limit parameter works: {len(data['alerts'])} alerts returned")
    
    def test_telegram_history_alert_structure(self):
        """Test that alert items have correct structure (if any exist)"""
        # First send a test message to ensure there's at least one alert
        requests.post(
            f"{BASE_URL}/api/telegram/test",
            json={"message": "History structure test"},
            headers={"Content-Type": "application/json"}
        )
        
        response = requests.get(f"{BASE_URL}/api/telegram/history")
        data = response.json()
        
        if len(data["alerts"]) > 0:
            alert = data["alerts"][0]
            # Check alert structure
            assert "type" in alert, "Alert missing 'type' field"
            assert "timestamp" in alert, "Alert missing 'timestamp' field"
            print(f"✓ Telegram history alert structure valid: type={alert.get('type')}")
        else:
            print("✓ Telegram history returned empty (no alerts yet)")


class TestDashboardAndCoreAPIs:
    """Test core dashboard APIs to ensure overall system is working"""
    
    def test_health_endpoint(self):
        """Test health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✓ Health endpoint working")
    
    def test_prices_aud_usd(self):
        """Test AUD/USD price endpoint"""
        response = requests.get(f"{BASE_URL}/api/prices/AUD_USD")
        assert response.status_code == 200
        data = response.json()
        assert "mid" in data or "price" in data or "pair" in data
        print("✓ AUD/USD price endpoint working")
    
    def test_prices_nzd_usd(self):
        """Test NZD/USD price endpoint"""
        response = requests.get(f"{BASE_URL}/api/prices/NZD_USD")
        assert response.status_code == 200
        data = response.json()
        assert "mid" in data or "price" in data or "pair" in data
        print("✓ NZD/USD price endpoint working")
    
    def test_signals_current(self):
        """Test current signals endpoint"""
        response = requests.get(f"{BASE_URL}/api/signals/current")
        assert response.status_code == 200
        print("✓ Signals endpoint working")
    
    def test_events_state(self):
        """Test event state endpoint"""
        response = requests.get(f"{BASE_URL}/api/events/state")
        assert response.status_code == 200
        data = response.json()
        assert "state" in data
        print("✓ Event state endpoint working")
    
    def test_settings_endpoint(self):
        """Test settings endpoint"""
        response = requests.get(f"{BASE_URL}/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert "kill_switch" in data
        print("✓ Settings endpoint working")
    
    def test_risk_status(self):
        """Test risk status endpoint"""
        response = requests.get(f"{BASE_URL}/api/risk/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        print("✓ Risk status endpoint working")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
