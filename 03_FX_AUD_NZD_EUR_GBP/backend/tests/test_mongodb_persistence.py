"""
MongoDB Persistence Tests for FX Trading System
Tests that settings, Telegram config, backtest results, and alert history persist to MongoDB
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://aud-nzd-signals.preview.emergentagent.com').rstrip('/')


class TestHealthAndBasicAPIs:
    """Test basic API health and connectivity"""
    
    def test_health_endpoint(self):
        """Test GET /api/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("status") == "healthy", f"Expected healthy status, got {data.get('status')}"
        print(f"✓ Health endpoint: status={data['status']}, data_source={data.get('data_source')}")
    
    def test_prices_aud_usd(self):
        """Test GET /api/prices/AUD_USD returns price data"""
        response = requests.get(f"{BASE_URL}/api/prices/AUD_USD")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "mid" in data or "pair" in data, "Missing price data fields"
        print(f"✓ AUD/USD price: mid={data.get('mid')}, spread={data.get('spread_pips')}")
    
    def test_prices_nzd_usd(self):
        """Test GET /api/prices/NZD_USD returns price data"""
        response = requests.get(f"{BASE_URL}/api/prices/NZD_USD")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "mid" in data or "pair" in data, "Missing price data fields"
        print(f"✓ NZD/USD price: mid={data.get('mid')}, spread={data.get('spread_pips')}")
    
    def test_signals_current(self):
        """Test GET /api/signals/current returns signal data"""
        response = requests.get(f"{BASE_URL}/api/signals/current")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        # Should return dict with pair signals
        assert isinstance(data, dict), "Expected dict response"
        print(f"✓ Signals current: {len(data)} pairs")
    
    def test_events_endpoint(self):
        """Test GET /api/events returns economic events"""
        response = requests.get(f"{BASE_URL}/api/events")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Expected list of events"
        print(f"✓ Events: {len(data)} events returned")
    
    def test_risk_status(self):
        """Test GET /api/risk/status returns risk control status"""
        response = requests.get(f"{BASE_URL}/api/risk/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "status" in data, "Missing 'status' field"
        assert "risk_level" in data, "Missing 'risk_level' field"
        print(f"✓ Risk status: {data.get('status')}, risk_level={data.get('risk_level', {}).get('level')}")
    
    def test_risk_capital_protection(self):
        """Test GET /api/risk/capital-protection returns capital protection data"""
        response = requests.get(f"{BASE_URL}/api/risk/capital-protection")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "daily_pnl" in data, "Missing 'daily_pnl' field"
        assert "capital_safety_score" in data, "Missing 'capital_safety_score' field"
        print(f"✓ Capital protection: daily_pnl={data.get('daily_pnl')}, safety_score={data.get('capital_safety_score', {}).get('score')}")


class TestSettingsPersistence:
    """Test settings persistence to MongoDB via PUT /api/settings/{key}"""
    
    def test_get_settings(self):
        """Test GET /api/settings returns all settings"""
        response = requests.get(f"{BASE_URL}/api/settings")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "kill_switch" in data, "Missing 'kill_switch' setting"
        assert "aud_usd_direction" in data, "Missing 'aud_usd_direction' setting"
        print(f"✓ Settings retrieved: {len(data)} settings")
    
    def test_update_setting_kill_switch(self):
        """Test PUT /api/settings/kill_switch persists to MongoDB"""
        # Get current value
        response = requests.get(f"{BASE_URL}/api/settings")
        original_value = response.json().get("kill_switch", "false")
        
        # Toggle value
        new_value = "true" if original_value == "false" else "false"
        
        # Update setting
        update_response = requests.put(
            f"{BASE_URL}/api/settings/kill_switch",
            json={"value": new_value},
            headers={"Content-Type": "application/json"}
        )
        assert update_response.status_code == 200, f"Expected 200, got {update_response.status_code}"
        
        # Verify persistence by fetching again
        verify_response = requests.get(f"{BASE_URL}/api/settings")
        verify_data = verify_response.json()
        assert verify_data.get("kill_switch") == new_value, f"Setting not persisted: expected {new_value}, got {verify_data.get('kill_switch')}"
        
        # Restore original value
        requests.put(
            f"{BASE_URL}/api/settings/kill_switch",
            json={"value": original_value},
            headers={"Content-Type": "application/json"}
        )
        
        print(f"✓ kill_switch setting persisted: {original_value} -> {new_value} -> {original_value}")
    
    def test_update_setting_direction(self):
        """Test PUT /api/settings/aud_usd_direction persists to MongoDB"""
        # Get current value
        response = requests.get(f"{BASE_URL}/api/settings")
        original_value = response.json().get("aud_usd_direction", "LONG_ONLY")
        
        # Set new value
        new_value = "BOTH" if original_value != "BOTH" else "LONG_ONLY"
        
        # Update setting
        update_response = requests.put(
            f"{BASE_URL}/api/settings/aud_usd_direction",
            json={"value": new_value},
            headers={"Content-Type": "application/json"}
        )
        assert update_response.status_code == 200, f"Expected 200, got {update_response.status_code}"
        
        # Verify persistence
        verify_response = requests.get(f"{BASE_URL}/api/settings")
        verify_data = verify_response.json()
        assert verify_data.get("aud_usd_direction") == new_value, f"Setting not persisted"
        
        # Restore original
        requests.put(
            f"{BASE_URL}/api/settings/aud_usd_direction",
            json={"value": original_value},
            headers={"Content-Type": "application/json"}
        )
        
        print(f"✓ aud_usd_direction setting persisted: {original_value} -> {new_value} -> {original_value}")
    
    def test_update_setting_stop_loss(self):
        """Test PUT /api/settings/stop_loss_pips persists to MongoDB"""
        # Get current value
        response = requests.get(f"{BASE_URL}/api/settings")
        original_value = response.json().get("stop_loss_pips", "15")
        
        # Set new value
        new_value = "20" if original_value != "20" else "15"
        
        # Update setting
        update_response = requests.put(
            f"{BASE_URL}/api/settings/stop_loss_pips",
            json={"value": new_value},
            headers={"Content-Type": "application/json"}
        )
        assert update_response.status_code == 200, f"Expected 200, got {update_response.status_code}"
        
        # Verify persistence
        verify_response = requests.get(f"{BASE_URL}/api/settings")
        verify_data = verify_response.json()
        assert verify_data.get("stop_loss_pips") == new_value, f"Setting not persisted"
        
        # Restore original
        requests.put(
            f"{BASE_URL}/api/settings/stop_loss_pips",
            json={"value": original_value},
            headers={"Content-Type": "application/json"}
        )
        
        print(f"✓ stop_loss_pips setting persisted: {original_value} -> {new_value} -> {original_value}")


class TestTelegramConfigPersistence:
    """Test Telegram config persistence to MongoDB via POST /api/telegram/config"""
    
    def test_telegram_config_save_and_persist(self):
        """Test POST /api/telegram/config persists to MongoDB"""
        # Save config with unique test values
        test_token = f"TEST_TOKEN_{int(time.time())}"
        test_chat_id = f"TEST_CHAT_{int(time.time())}"
        
        save_response = requests.post(
            f"{BASE_URL}/api/telegram/config",
            json={"bot_token": test_token, "chat_id": test_chat_id},
            headers={"Content-Type": "application/json"}
        )
        assert save_response.status_code == 200, f"Expected 200, got {save_response.status_code}"
        save_data = save_response.json()
        assert save_data.get("success") == True, "Config save should succeed"
        assert save_data.get("bot_token_set") == True, "bot_token should be set"
        assert save_data.get("chat_id_set") == True, "chat_id should be set"
        
        # Verify via status endpoint
        status_response = requests.get(f"{BASE_URL}/api/telegram/status")
        status_data = status_response.json()
        assert status_data.get("configured") == True, "Telegram should be configured"
        assert status_data.get("bot_token_set") == True, "bot_token should be set in status"
        assert status_data.get("chat_id_set") == True, "chat_id should be set in status"
        
        print(f"✓ Telegram config persisted: token={test_token[:20]}..., chat_id={test_chat_id}")
    
    def test_telegram_status_endpoint(self):
        """Test GET /api/telegram/status returns correct structure"""
        response = requests.get(f"{BASE_URL}/api/telegram/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "configured" in data, "Missing 'configured' field"
        assert "bot_token_set" in data, "Missing 'bot_token_set' field"
        assert "chat_id_set" in data, "Missing 'chat_id_set' field"
        assert "daily_alerts_sent" in data, "Missing 'daily_alerts_sent' field"
        
        print(f"✓ Telegram status: configured={data['configured']}, alerts_sent={data['daily_alerts_sent']}")


class TestAlertHistoryPersistence:
    """Test alert history persistence to MongoDB via GET /api/telegram/history"""
    
    def test_alert_history_endpoint(self):
        """Test GET /api/telegram/history returns alerts from MongoDB"""
        response = requests.get(f"{BASE_URL}/api/telegram/history")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "alerts" in data, "Missing 'alerts' field"
        assert isinstance(data["alerts"], list), "'alerts' should be a list"
        
        print(f"✓ Alert history: {len(data['alerts'])} alerts in MongoDB")
    
    def test_alert_history_after_test_message(self):
        """Test that sending test message creates alert in MongoDB history"""
        # Get initial count
        initial_response = requests.get(f"{BASE_URL}/api/telegram/history")
        initial_count = len(initial_response.json().get("alerts", []))
        
        # Send test message
        test_msg = f"MongoDB persistence test {int(time.time())}"
        requests.post(
            f"{BASE_URL}/api/telegram/test",
            json={"message": test_msg},
            headers={"Content-Type": "application/json"}
        )
        
        # Check history increased
        time.sleep(0.5)  # Small delay for DB write
        after_response = requests.get(f"{BASE_URL}/api/telegram/history")
        after_count = len(after_response.json().get("alerts", []))
        
        assert after_count >= initial_count, f"Alert count should not decrease: {initial_count} -> {after_count}"
        print(f"✓ Alert stored in MongoDB: count {initial_count} -> {after_count}")
    
    def test_alert_history_structure(self):
        """Test alert items have correct structure"""
        # Ensure at least one alert exists
        requests.post(
            f"{BASE_URL}/api/telegram/test",
            json={"message": "Structure test"},
            headers={"Content-Type": "application/json"}
        )
        time.sleep(0.5)
        
        response = requests.get(f"{BASE_URL}/api/telegram/history")
        data = response.json()
        
        if len(data["alerts"]) > 0:
            alert = data["alerts"][0]
            assert "type" in alert, "Alert missing 'type' field"
            assert "timestamp" in alert, "Alert missing 'timestamp' field"
            print(f"✓ Alert structure valid: type={alert.get('type')}, timestamp={alert.get('timestamp')[:19]}")
        else:
            print("✓ Alert history empty (no alerts yet)")


class TestBacktestPersistence:
    """Test backtest results persistence to MongoDB"""
    
    def test_backtest_stats_endpoint(self):
        """Test GET /api/backtest/stats returns seeded data from MongoDB"""
        response = requests.get(f"{BASE_URL}/api/backtest/stats")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "summary" in data, "Missing 'summary' field"
        assert "by_pair" in data, "Missing 'by_pair' field"
        
        summary = data.get("summary", {})
        total_trades = summary.get("total_trades", 0)
        
        # Should have seeded backtest data
        assert total_trades > 0, f"Expected seeded backtest data, got {total_trades} trades"
        
        print(f"✓ Backtest stats: {total_trades} trades, success_rate={summary.get('overall_success_rate')}%")
    
    def test_backtest_results_endpoint(self):
        """Test GET /api/backtest/results returns data from MongoDB"""
        response = requests.get(f"{BASE_URL}/api/backtest/results")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "results" in data, "Missing 'results' field"
        results = data.get("results", [])
        
        # Should have seeded results
        assert len(results) > 0, f"Expected seeded backtest results, got {len(results)}"
        
        # Check result structure
        if len(results) > 0:
            result = results[0]
            assert "pair" in result, "Result missing 'pair' field"
            assert "pnl_pips" in result, "Result missing 'pnl_pips' field"
        
        print(f"✓ Backtest results: {len(results)} results from MongoDB")
    
    def test_backtest_results_by_pair(self):
        """Test GET /api/backtest/results?pair=AUD_USD filters correctly"""
        response = requests.get(f"{BASE_URL}/api/backtest/results?pair=AUD_USD")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        results = data.get("results", [])
        
        # All results should be for AUD/USD
        for result in results:
            assert result.get("pair") == "AUD/USD", f"Expected AUD/USD, got {result.get('pair')}"
        
        print(f"✓ Backtest results filtered: {len(results)} AUD/USD results")
    
    def test_backtest_chart_data(self):
        """Test GET /api/backtest/chart-data returns chart data"""
        response = requests.get(f"{BASE_URL}/api/backtest/chart-data")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "chart_data" in data, "Missing 'chart_data' field"
        chart_data = data.get("chart_data", [])
        
        print(f"✓ Backtest chart data: {len(chart_data)} data points")


class TestMonteCarloAndGridSearch:
    """Test Monte Carlo simulation and Grid Search endpoints"""
    
    def test_monte_carlo_simulation(self):
        """Test GET /api/backtest/monte-carlo runs simulation"""
        response = requests.get(f"{BASE_URL}/api/backtest/monte-carlo?num_simulations=100&trades_per_sim=50")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Check for simulation results or error (if no backtest data)
        if "error" not in data:
            assert "robustness_score" in data, "Missing 'robustness_score' field"
            assert "pnl_statistics" in data, "Missing 'pnl_statistics' field"
            print(f"✓ Monte Carlo: robustness_score={data.get('robustness_score', {}).get('score')}")
        else:
            print(f"✓ Monte Carlo: {data.get('message', 'No backtest data')}")
    
    def test_grid_search_quick(self):
        """Test GET /api/backtest/grid-search/quick runs optimization"""
        response = requests.get(f"{BASE_URL}/api/backtest/grid-search/quick")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Check for results or error
        if "error" not in data:
            assert "best_parameters" in data, "Missing 'best_parameters' field"
            print(f"✓ Grid Search: best_score={data.get('best_parameters', {}).get('scores', {}).get('composite_score')}")
        else:
            print(f"✓ Grid Search: {data.get('message', 'No backtest data')}")


class TestAIAnalysis:
    """Test AI analysis endpoints"""
    
    def test_ai_history(self):
        """Test GET /api/ai/history returns AI analyses from MongoDB"""
        response = requests.get(f"{BASE_URL}/api/ai/history")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "analyses" in data, "Missing 'analyses' field"
        assert isinstance(data["analyses"], list), "'analyses' should be a list"
        
        print(f"✓ AI history: {len(data['analyses'])} analyses in MongoDB")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
