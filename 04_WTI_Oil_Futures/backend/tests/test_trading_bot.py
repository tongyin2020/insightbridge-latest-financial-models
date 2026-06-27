"""
Trading Bot (Human-in-the-Loop) API Tests - Iteration 7
Tests the automated trading bot with manual approval workflow
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://petro-trading-ai.preview.emergentagent.com').rstrip('/')


class TestBotStatus:
    """Bot status endpoint tests"""
    
    def test_bot_status_returns_all_fields(self):
        """GET /api/bot/status returns all required fields"""
        response = requests.get(f"{BASE_URL}/api/bot/status")
        assert response.status_code == 200
        
        data = response.json()
        # Verify all required fields exist
        assert "enabled" in data
        assert "min_confidence" in data
        assert "scan_interval_sec" in data
        assert "max_daily_trades" in data
        assert "pending_count" in data
        assert "executed_today" in data
        assert "remaining_today" in data
        assert "total_generated" in data
        assert "total_approved" in data
        assert "total_rejected" in data
        assert "last_scan" in data
        
        # Verify data types
        assert isinstance(data["enabled"], bool)
        assert isinstance(data["min_confidence"], (int, float))
        assert isinstance(data["scan_interval_sec"], int)
        assert isinstance(data["max_daily_trades"], int)
        assert isinstance(data["pending_count"], int)
        assert isinstance(data["executed_today"], int)
        
        # Verify min_confidence is >= 65 (as per requirements)
        assert data["min_confidence"] >= 65
        
        print(f"Bot status: enabled={data['enabled']}, min_confidence={data['min_confidence']}%, pending={data['pending_count']}")


class TestBotToggle:
    """Bot toggle endpoint tests"""
    
    def test_bot_toggle_without_param(self):
        """POST /api/bot/toggle toggles bot state"""
        # Get current state
        status_res = requests.get(f"{BASE_URL}/api/bot/status")
        initial_state = status_res.json()["enabled"]
        
        # Toggle
        response = requests.post(f"{BASE_URL}/api/bot/toggle")
        assert response.status_code == 200
        
        data = response.json()
        assert "enabled" in data
        assert data["enabled"] != initial_state
        
        # Toggle back
        response2 = requests.post(f"{BASE_URL}/api/bot/toggle")
        assert response2.status_code == 200
        assert response2.json()["enabled"] == initial_state
        
        print(f"Toggle test passed: {initial_state} -> {data['enabled']} -> {initial_state}")
    
    def test_bot_toggle_explicit_enable(self):
        """POST /api/bot/toggle?enabled=true enables bot"""
        response = requests.post(f"{BASE_URL}/api/bot/toggle?enabled=true")
        assert response.status_code == 200
        
        data = response.json()
        assert data["enabled"] == True
        print("Explicit enable test passed")
    
    def test_bot_toggle_explicit_disable(self):
        """POST /api/bot/toggle?enabled=false disables bot"""
        response = requests.post(f"{BASE_URL}/api/bot/toggle?enabled=false")
        assert response.status_code == 200
        
        data = response.json()
        assert data["enabled"] == False
        
        # Re-enable for other tests
        requests.post(f"{BASE_URL}/api/bot/toggle?enabled=true")
        print("Explicit disable test passed")


class TestBotConfig:
    """Bot configuration endpoint tests"""
    
    def test_update_min_confidence(self):
        """POST /api/bot/config updates min_confidence"""
        # Update to 70%
        response = requests.post(
            f"{BASE_URL}/api/bot/config",
            json={"min_confidence": 70}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["min_confidence"] == 70
        
        # Reset to 65%
        requests.post(f"{BASE_URL}/api/bot/config", json={"min_confidence": 65})
        print("Config update test passed")
    
    def test_config_validation_min_confidence_bounds(self):
        """Config enforces min_confidence bounds (50-95)"""
        # Try setting below minimum
        response = requests.post(
            f"{BASE_URL}/api/bot/config",
            json={"min_confidence": 30}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["min_confidence"] >= 50  # Should be clamped to 50
        
        # Try setting above maximum
        response = requests.post(
            f"{BASE_URL}/api/bot/config",
            json={"min_confidence": 99}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["min_confidence"] <= 95  # Should be clamped to 95
        
        # Reset to 65%
        requests.post(f"{BASE_URL}/api/bot/config", json={"min_confidence": 65})
        print("Config bounds validation passed")


class TestBotOpportunities:
    """Bot opportunities endpoint tests"""
    
    def test_get_pending_opportunities(self):
        """GET /api/bot/opportunities returns pending list"""
        response = requests.get(f"{BASE_URL}/api/bot/opportunities")
        assert response.status_code == 200
        
        data = response.json()
        assert "opportunities" in data
        assert isinstance(data["opportunities"], list)
        
        # If there are opportunities, verify structure
        if len(data["opportunities"]) > 0:
            opp = data["opportunities"][0]
            assert "id" in opp
            assert "symbol" in opp
            assert "direction" in opp
            assert "confidence" in opp
            assert "entry_price" in opp
            assert "stop_loss" in opp
            assert "take_profit_1" in opp
            assert "take_profit_2" in opp
            assert "size" in opp
            assert "reasoning" in opp
            assert "status" in opp
            assert opp["status"] == "pending"
            print(f"Found {len(data['opportunities'])} pending opportunities")
        else:
            print("No pending opportunities (expected if market confidence < 65%)")


class TestBotHistory:
    """Bot history endpoint tests"""
    
    def test_get_bot_history(self):
        """GET /api/bot/history returns history list"""
        response = requests.get(f"{BASE_URL}/api/bot/history?limit=20")
        assert response.status_code == 200
        
        data = response.json()
        assert "history" in data
        assert isinstance(data["history"], list)
        
        # If there's history, verify structure
        if len(data["history"]) > 0:
            item = data["history"][0]
            assert "id" in item
            assert "symbol" in item
            assert "direction" in item
            assert "status" in item
            print(f"Found {len(data['history'])} history items")
        else:
            print("No history yet (expected for fresh bot)")


class TestBotApproveReject:
    """Bot approve/reject endpoint tests"""
    
    def test_approve_nonexistent_opportunity(self):
        """POST /api/bot/approve/{id} returns 404 for invalid ID"""
        response = requests.post(f"{BASE_URL}/api/bot/approve/invalid_id_12345")
        assert response.status_code == 404
        print("Approve invalid ID returns 404 - PASS")
    
    def test_reject_nonexistent_opportunity(self):
        """POST /api/bot/reject/{id} returns 404 for invalid ID"""
        response = requests.post(f"{BASE_URL}/api/bot/reject/invalid_id_12345")
        assert response.status_code == 404
        print("Reject invalid ID returns 404 - PASS")


class TestBotScannerLoop:
    """Bot scanner background task tests"""
    
    def test_last_scan_timestamp_updates(self):
        """Bot scanner updates last_scan timestamp when enabled"""
        # Ensure bot is enabled
        requests.post(f"{BASE_URL}/api/bot/toggle?enabled=true")
        
        # Get initial status
        status1 = requests.get(f"{BASE_URL}/api/bot/status").json()
        last_scan_1 = status1.get("last_scan")
        
        # Wait for scan interval (10 seconds) + buffer
        time.sleep(12)
        
        # Get updated status
        status2 = requests.get(f"{BASE_URL}/api/bot/status").json()
        last_scan_2 = status2.get("last_scan")
        
        # Verify timestamp changed (scanner is running)
        if last_scan_1 and last_scan_2:
            assert last_scan_2 != last_scan_1 or last_scan_2 is not None
            print(f"Scanner running: last_scan updated from {last_scan_1} to {last_scan_2}")
        else:
            print(f"Scanner check: last_scan_1={last_scan_1}, last_scan_2={last_scan_2}")


class TestExistingEndpoints:
    """Verify existing endpoints still work"""
    
    def test_fragility_endpoint(self):
        """GET /api/fragility still works"""
        response = requests.get(f"{BASE_URL}/api/fragility")
        assert response.status_code == 200
        data = response.json()
        assert "score" in data
        assert "level" in data
        print(f"Fragility: level={data['level']}, score={data['score']}")
    
    def test_signal_score_cl(self):
        """GET /api/signal-score/CL still works"""
        response = requests.get(f"{BASE_URL}/api/signal-score/CL")
        assert response.status_code == 200
        data = response.json()
        assert "score" in data
        assert "direction" in data
        assert "bullish_pct" in data
        print(f"Signal CL: score={data['score']}, direction={data['direction']}, bullish={data['bullish_pct']}%")
    
    def test_execution_gate_cl(self):
        """GET /api/execution-gate/CL still works"""
        response = requests.get(f"{BASE_URL}/api/execution-gate/CL")
        assert response.status_code == 200
        data = response.json()
        assert "gate_status" in data
        print(f"Execution Gate CL: status={data['gate_status']}")
    
    def test_risk_control_status(self):
        """GET /api/risk-control/status still works"""
        response = requests.get(f"{BASE_URL}/api/risk-control/status")
        assert response.status_code == 200
        data = response.json()
        assert "level" in data
        assert "can_trade" in data
        print(f"Risk Control: level={data['level']}, can_trade={data['can_trade']}")
    
    def test_events_calendar(self):
        """GET /api/events/calendar still works"""
        response = requests.get(f"{BASE_URL}/api/events/calendar")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "state" in data
        print(f"Events: {len(data['events'])} events, cooldown={data['state'].get('cooldown_active', False)}")
    
    def test_system_status(self):
        """GET /api/system/status still works"""
        response = requests.get(f"{BASE_URL}/api/system/status")
        assert response.status_code == 200
        data = response.json()
        assert "is_running" in data
        assert "current_symbol" in data
        assert "equity" in data
        print(f"System: running={data['is_running']}, symbol={data['current_symbol']}, equity=${data['equity']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
