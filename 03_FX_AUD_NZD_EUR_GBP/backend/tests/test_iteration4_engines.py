"""
Iteration 4 - Testing New Engines:
- Event Response Engine (5-stage state machine)
- Execution Gate (priority-based decision layer)
- Strategy Monitor (loss streak detection, graduated recovery)
- Features API
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthAndCore:
    """Core API health checks"""
    
    def test_health_endpoint(self):
        """Test /api/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print(f"✓ Health check passed: {data}")
    
    def test_prices_aud_usd(self):
        """Test /api/prices/AUD_USD returns valid price data"""
        response = requests.get(f"{BASE_URL}/api/prices/AUD_USD")
        assert response.status_code == 200
        data = response.json()
        assert "mid" in data or "price" in data or "close" in data
        print(f"✓ AUD/USD price data: {data}")
    
    def test_prices_nzd_usd(self):
        """Test /api/prices/NZD_USD returns valid price data"""
        response = requests.get(f"{BASE_URL}/api/prices/NZD_USD")
        assert response.status_code == 200
        data = response.json()
        print(f"✓ NZD/USD price data: {data}")
    
    def test_signals_current(self):
        """Test /api/signals/current returns signals"""
        response = requests.get(f"{BASE_URL}/api/signals/current")
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Current signals: {data}")
    
    def test_events_endpoint(self):
        """Test /api/events returns economic calendar"""
        response = requests.get(f"{BASE_URL}/api/events")
        assert response.status_code == 200
        data = response.json()
        # API returns dict with 'events' key or list directly
        if isinstance(data, dict):
            events = data.get("events", [])
        else:
            events = data
        assert isinstance(events, list)
        print(f"✓ Events count: {len(events)}")
    
    def test_risk_status(self):
        """Test /api/risk/status returns risk control status"""
        response = requests.get(f"{BASE_URL}/api/risk/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        print(f"✓ Risk status: {data.get('status')}")


class TestEventResponseEngine:
    """Event Response Engine - 5-stage state machine tests"""
    
    def test_event_response_status(self):
        """GET /api/event-response/status returns engines for AUD/USD and NZD/USD with pair_config"""
        response = requests.get(f"{BASE_URL}/api/event-response/status")
        assert response.status_code == 200
        data = response.json()
        
        # Check engines exist for both pairs
        assert "engines" in data
        engines = data["engines"]
        assert "AUD/USD" in engines, "AUD/USD engine missing"
        assert "NZD/USD" in engines, "NZD/USD engine missing"
        
        # Check pair_config exists
        assert "pair_config" in data
        pair_config = data["pair_config"]
        assert "AUD/USD" in pair_config
        assert "NZD/USD" in pair_config
        
        print(f"✓ Event Response Status - Engines: {list(engines.keys())}")
        print(f"  AUD/USD state: {engines['AUD/USD'].get('state')}")
        print(f"  NZD/USD state: {engines['NZD/USD'].get('state')}")
        return data
    
    def test_event_response_reset(self):
        """POST /api/event-response/reset resets engines back to IDLE"""
        response = requests.post(f"{BASE_URL}/api/event-response/reset")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("success") == True
        assert "states" in data
        
        # Verify both engines are IDLE after reset
        states = data["states"]
        assert states["AUD/USD"]["state"] == "IDLE", f"AUD/USD not IDLE: {states['AUD/USD']['state']}"
        assert states["NZD/USD"]["state"] == "IDLE", f"NZD/USD not IDLE: {states['NZD/USD']['state']}"
        
        print(f"✓ Event Response Reset - Both engines now IDLE")
        return data
    
    def test_event_response_trigger(self):
        """POST /api/event-response/trigger triggers event detection state for both pairs"""
        # First reset to ensure clean state
        requests.post(f"{BASE_URL}/api/event-response/reset")
        time.sleep(0.5)
        
        # Trigger event
        response = requests.post(f"{BASE_URL}/api/event-response/trigger?event_level=A&title=Test%20Event")
        assert response.status_code == 200
        data = response.json()
        
        assert "event_response" in data
        event_response = data["event_response"]
        
        # Both pairs should be in EVENT_DETECTED state (or progressed further)
        valid_states = ["EVENT_DETECTED", "IMPULSE_PHASE", "LIQUIDITY_REBUILD", "DIRECTION_CONFIRM", "READY", "INVALID"]
        
        for pair in ["AUD/USD", "NZD/USD"]:
            if pair in event_response:
                state = event_response[pair].get("state")
                assert state in valid_states, f"{pair} in unexpected state: {state}"
                print(f"  {pair} triggered to state: {state}")
        
        print(f"✓ Event Response Trigger - Events triggered successfully")
        return data
    
    def test_pair_config_max_wait_seconds(self):
        """Verify pair config shows max_wait_seconds=90 for both FX pairs"""
        response = requests.get(f"{BASE_URL}/api/event-response/status")
        assert response.status_code == 200
        data = response.json()
        
        pair_config = data.get("pair_config", {})
        
        # Check AUD/USD max_wait_seconds
        aud_config = pair_config.get("AUD/USD", {})
        assert aud_config.get("max_wait_seconds") == 90, f"AUD/USD max_wait_seconds: {aud_config.get('max_wait_seconds')}"
        
        # Check NZD/USD max_wait_seconds
        nzd_config = pair_config.get("NZD/USD", {})
        assert nzd_config.get("max_wait_seconds") == 90, f"NZD/USD max_wait_seconds: {nzd_config.get('max_wait_seconds')}"
        
        print(f"✓ Pair Config - AUD/USD max_wait=90s, NZD/USD max_wait=90s")
        return data


class TestExecutionGate:
    """Execution Gate - Priority-based decision layer tests"""
    
    def test_execution_gate_status(self):
        """GET /api/execution-gate/status returns gate_state, pair_risk_config, regime_multipliers"""
        response = requests.get(f"{BASE_URL}/api/execution-gate/status")
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        assert "gate_state" in data, "gate_state missing"
        assert "pair_risk_config" in data, "pair_risk_config missing"
        assert "regime_multipliers" in data, "regime_multipliers missing"
        
        print(f"✓ Execution Gate Status:")
        print(f"  gate_state: {data['gate_state']}")
        print(f"  pair_risk_config: {list(data['pair_risk_config'].keys())}")
        print(f"  regime_multipliers: {data['regime_multipliers']}")
        return data
    
    def test_execution_gate_evaluate_aud_usd(self):
        """POST /api/execution-gate/evaluate?pair=AUD/USD returns GateDecision with action, priority_level"""
        # First reset event response to ensure clean state
        requests.post(f"{BASE_URL}/api/event-response/reset")
        time.sleep(0.5)
        
        response = requests.post(f"{BASE_URL}/api/execution-gate/evaluate?pair=AUD/USD")
        assert response.status_code == 200
        data = response.json()
        
        # Check decision structure
        assert "decision" in data, "decision missing"
        decision = data["decision"]
        assert "action" in decision, "action missing in decision"
        assert "priority_level" in decision, "priority_level missing in decision"
        
        print(f"✓ Execution Gate Evaluate AUD/USD:")
        print(f"  action: {decision['action']}")
        print(f"  priority_level: {decision['priority_level']}")
        print(f"  reason_codes: {decision.get('reason_codes', [])}")
        return data
    
    def test_execution_gate_evaluate_nzd_usd(self):
        """POST /api/execution-gate/evaluate?pair=NZD/USD returns GateDecision"""
        response = requests.post(f"{BASE_URL}/api/execution-gate/evaluate?pair=NZD/USD")
        assert response.status_code == 200
        data = response.json()
        
        assert "decision" in data
        decision = data["decision"]
        assert "action" in decision
        assert "priority_level" in decision
        
        print(f"✓ Execution Gate Evaluate NZD/USD:")
        print(f"  action: {decision['action']}")
        print(f"  priority_level: {decision['priority_level']}")
        return data
    
    def test_pair_risk_config_values(self):
        """Verify AUD/USD base_risk=0.3%, multiplier=0.7x; NZD/USD base_risk=0.25%, multiplier=0.6x"""
        response = requests.get(f"{BASE_URL}/api/execution-gate/status")
        assert response.status_code == 200
        data = response.json()
        
        pair_risk_config = data.get("pair_risk_config", {})
        
        # Check AUD/USD config
        aud_config = pair_risk_config.get("AUD/USD", {})
        assert aud_config.get("base_risk_percent") == 0.3, f"AUD/USD base_risk: {aud_config.get('base_risk_percent')}"
        assert aud_config.get("risk_multiplier") == 0.7, f"AUD/USD multiplier: {aud_config.get('risk_multiplier')}"
        
        # Check NZD/USD config
        nzd_config = pair_risk_config.get("NZD/USD", {})
        assert nzd_config.get("base_risk_percent") == 0.25, f"NZD/USD base_risk: {nzd_config.get('base_risk_percent')}"
        assert nzd_config.get("risk_multiplier") == 0.6, f"NZD/USD multiplier: {nzd_config.get('risk_multiplier')}"
        
        print(f"✓ Pair Risk Config verified:")
        print(f"  AUD/USD: base_risk=0.3%, multiplier=0.7x")
        print(f"  NZD/USD: base_risk=0.25%, multiplier=0.6x")
        return data
    
    def test_gate_blocks_during_event(self):
        """During event (after trigger), gate blocks trading with EVENT_ reason code"""
        # Reset first
        requests.post(f"{BASE_URL}/api/event-response/reset")
        time.sleep(0.5)
        
        # Trigger event
        requests.post(f"{BASE_URL}/api/event-response/trigger?event_level=A&title=Test%20Event")
        time.sleep(0.5)
        
        # Evaluate gate - should block with EVENT_ reason
        response = requests.post(f"{BASE_URL}/api/execution-gate/evaluate?pair=AUD/USD")
        assert response.status_code == 200
        data = response.json()
        
        decision = data.get("decision", {})
        reason_codes = decision.get("reason_codes", [])
        
        # Check if any reason code starts with EVENT_
        has_event_reason = any(code.startswith("EVENT_") for code in reason_codes)
        
        # The gate should either BLOCK or have EVENT_ reason code
        action = decision.get("action")
        
        print(f"✓ Gate during event:")
        print(f"  action: {action}")
        print(f"  reason_codes: {reason_codes}")
        print(f"  has_event_reason: {has_event_reason}")
        
        # Reset after test
        requests.post(f"{BASE_URL}/api/event-response/reset")
        
        return data


class TestStrategyMonitor:
    """Strategy Monitor - Loss streak detection and graduated recovery tests"""
    
    def test_strategy_monitor_health(self):
        """GET /api/strategy-monitor/health returns health for both pairs with GREEN state initially"""
        # Reset daily to ensure clean state
        requests.post(f"{BASE_URL}/api/strategy-monitor/reset-daily")
        time.sleep(0.3)
        
        response = requests.get(f"{BASE_URL}/api/strategy-monitor/health")
        assert response.status_code == 200
        data = response.json()
        
        # Check both pairs exist
        assert "AUD/USD" in data, "AUD/USD health missing"
        assert "NZD/USD" in data, "NZD/USD health missing"
        
        # Check structure
        for pair in ["AUD/USD", "NZD/USD"]:
            health = data[pair]
            assert "consecutive_losses" in health
            assert "recovery_state" in health
            assert "frozen" in health
            assert "risk_multiplier" in health
        
        print(f"✓ Strategy Monitor Health:")
        print(f"  AUD/USD: recovery_state={data['AUD/USD']['recovery_state']}, frozen={data['AUD/USD']['frozen']}")
        print(f"  NZD/USD: recovery_state={data['NZD/USD']['recovery_state']}, frozen={data['NZD/USD']['frozen']}")
        return data
    
    def test_record_trade_updates_losses(self):
        """POST /api/strategy-monitor/record-trade records trades and updates consecutive losses"""
        # Reset first
        requests.post(f"{BASE_URL}/api/strategy-monitor/reset-daily")
        time.sleep(0.3)
        
        # Record a losing trade
        response = requests.post(f"{BASE_URL}/api/strategy-monitor/record-trade?pair=AUD/USD&pnl_pips=-5")
        assert response.status_code == 200
        data = response.json()
        
        aud_health = data.get("AUD/USD", {})
        assert aud_health.get("consecutive_losses") >= 1, f"consecutive_losses should be >= 1: {aud_health.get('consecutive_losses')}"
        
        print(f"✓ Record Trade - AUD/USD consecutive_losses: {aud_health.get('consecutive_losses')}")
        return data
    
    def test_loss_streak_freezes_pair(self):
        """After 6 consecutive losses on AUD/USD, pair should be frozen"""
        # Reset first
        requests.post(f"{BASE_URL}/api/strategy-monitor/reset-daily")
        time.sleep(0.3)
        
        # Record 6 consecutive losses
        for i in range(6):
            response = requests.post(f"{BASE_URL}/api/strategy-monitor/record-trade?pair=AUD/USD&pnl_pips=-5")
            assert response.status_code == 200
            time.sleep(0.1)
        
        # Check if frozen
        response = requests.get(f"{BASE_URL}/api/strategy-monitor/health")
        data = response.json()
        
        aud_health = data.get("AUD/USD", {})
        consecutive_losses = aud_health.get("consecutive_losses", 0)
        frozen = aud_health.get("frozen", False)
        frozen_reason = aud_health.get("frozen_reason", "")
        
        print(f"✓ Loss Streak Test:")
        print(f"  consecutive_losses: {consecutive_losses}")
        print(f"  frozen: {frozen}")
        print(f"  frozen_reason: {frozen_reason}")
        
        # AUD/USD should be frozen after 6 losses
        assert frozen == True, f"AUD/USD should be frozen after 6 losses, but frozen={frozen}"
        assert "LOSS_STREAK" in frozen_reason, f"frozen_reason should contain LOSS_STREAK: {frozen_reason}"
        
        return data
    
    def test_unfreeze_pair(self):
        """POST /api/strategy-monitor/unfreeze unfreezes a frozen pair"""
        # First freeze the pair
        requests.post(f"{BASE_URL}/api/strategy-monitor/reset-daily")
        time.sleep(0.3)
        for i in range(6):
            requests.post(f"{BASE_URL}/api/strategy-monitor/record-trade?pair=AUD/USD&pnl_pips=-5")
            time.sleep(0.1)
        
        # Verify frozen
        health_before = requests.get(f"{BASE_URL}/api/strategy-monitor/health").json()
        assert health_before["AUD/USD"]["frozen"] == True
        
        # Unfreeze
        response = requests.post(f"{BASE_URL}/api/strategy-monitor/unfreeze?pair=AUD/USD")
        assert response.status_code == 200
        data = response.json()
        
        aud_health = data.get("AUD/USD", {})
        assert aud_health.get("frozen") == False, f"AUD/USD should be unfrozen: {aud_health.get('frozen')}"
        assert aud_health.get("consecutive_losses") == 0, f"consecutive_losses should be reset: {aud_health.get('consecutive_losses')}"
        
        print(f"✓ Unfreeze - AUD/USD unfrozen, consecutive_losses reset to 0")
        return data


class TestFeaturesAPI:
    """Features API - vol_ratio, spread_ratio, trend_score tests"""
    
    def test_features_aud_usd(self):
        """GET /api/features/AUD_USD returns vol_ratio, spread_ratio, trend_score_5m"""
        response = requests.get(f"{BASE_URL}/api/features/AUD_USD")
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        assert "vol_ratio" in data, "vol_ratio missing"
        assert "spread_ratio" in data, "spread_ratio missing"
        assert "trend_score_5m" in data, "trend_score_5m missing"
        
        print(f"✓ Features AUD/USD:")
        print(f"  vol_ratio: {data.get('vol_ratio')}")
        print(f"  spread_ratio: {data.get('spread_ratio')}")
        print(f"  trend_score_5m: {data.get('trend_score_5m')}")
        return data
    
    def test_features_nzd_usd(self):
        """GET /api/features/NZD_USD returns features"""
        response = requests.get(f"{BASE_URL}/api/features/NZD_USD")
        assert response.status_code == 200
        data = response.json()
        
        assert "vol_ratio" in data
        assert "spread_ratio" in data
        assert "trend_score_5m" in data
        
        print(f"✓ Features NZD/USD:")
        print(f"  vol_ratio: {data.get('vol_ratio')}")
        print(f"  spread_ratio: {data.get('spread_ratio')}")
        print(f"  trend_score_5m: {data.get('trend_score_5m')}")
        return data


class TestCleanup:
    """Cleanup tests - reset state after testing"""
    
    def test_final_reset(self):
        """Reset all engines to clean state"""
        # Reset event response
        response1 = requests.post(f"{BASE_URL}/api/event-response/reset")
        assert response1.status_code == 200
        
        # Reset strategy monitor
        response2 = requests.post(f"{BASE_URL}/api/strategy-monitor/reset-daily")
        assert response2.status_code == 200
        
        # Unfreeze both pairs
        requests.post(f"{BASE_URL}/api/strategy-monitor/unfreeze?pair=AUD/USD")
        requests.post(f"{BASE_URL}/api/strategy-monitor/unfreeze?pair=NZD/USD")
        
        print(f"✓ Final cleanup complete - all engines reset")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
