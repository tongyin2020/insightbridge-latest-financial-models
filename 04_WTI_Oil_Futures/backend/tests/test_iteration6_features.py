"""
Iteration 6 Test Suite - 9 New Features from FX Trading Dashboard
Tests: Fragility Engine, Event Engine, Risk Control Center, Execution Gate, Signal Scorer,
       Daily PnL, Exit Tiers, Slippage Stats, Spread Monitoring
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://petro-trading-ai.preview.emergentagent.com').rstrip('/')


class TestFragilityEngine:
    """Tests for Fragility Engine - market vulnerability assessment"""
    
    def test_fragility_endpoint_returns_required_fields(self):
        """GET /api/fragility should return level, score, components, triggers, size_multiplier"""
        response = requests.get(f"{BASE_URL}/api/fragility")
        assert response.status_code == 200
        
        data = response.json()
        # Required fields
        assert "level" in data
        assert "score" in data
        assert "components" in data
        assert "triggers" in data
        assert "size_multiplier" in data
        
        # Level should be one of: low, moderate, high, extreme
        assert data["level"] in ["low", "moderate", "high", "extreme"]
        
        # Score should be 0-100
        assert 0 <= data["score"] <= 100
        
        # Components should have 5 factors
        components = data["components"]
        assert "spread" in components
        assert "volatility" in components
        assert "price_shock" in components
        assert "liquidity" in components
        assert "regime" in components
        
        # Size multiplier should be 0-1
        assert 0 <= data["size_multiplier"] <= 1
        
        print(f"✓ Fragility: level={data['level']}, score={data['score']:.1f}, size_mult={data['size_multiplier']}")


class TestEventEngine:
    """Tests for Event Engine & Economic Calendar"""
    
    def test_event_calendar_returns_events_and_state(self):
        """GET /api/events/calendar should return events list and state"""
        response = requests.get(f"{BASE_URL}/api/events/calendar?hours_ahead=48")
        assert response.status_code == 200
        
        data = response.json()
        assert "events" in data
        assert "state" in data
        
        # Events should be a list
        assert isinstance(data["events"], list)
        assert len(data["events"]) > 0
        
        # Check event structure
        event = data["events"][0]
        assert "id" in event
        assert "title" in event
        assert "category" in event
        assert "impact" in event
        assert "oil_relevance" in event
        
        # State should have cooldown info
        state = data["state"]
        assert "cooldown_active" in state
        assert "risk_modifier" in state
        assert "halt_trading" in state
        
        print(f"✓ Event Calendar: {len(data['events'])} events, cooldown={state['cooldown_active']}")
    
    def test_event_state_endpoint(self):
        """GET /api/events/state should return cooldown and risk modifier"""
        response = requests.get(f"{BASE_URL}/api/events/state")
        assert response.status_code == 200
        
        data = response.json()
        assert "cooldown_active" in data
        assert "cooldown_reason" in data
        assert "cooldown_remaining_sec" in data
        assert "halt_trading" in data
        assert "risk_modifier" in data
        
        # Risk modifier should be 0-1
        assert 0 <= data["risk_modifier"] <= 1
        
        print(f"✓ Event State: cooldown={data['cooldown_active']}, risk_mod={data['risk_modifier']}")
    
    def test_event_trigger_activates_cooldown(self):
        """POST /api/events/trigger/{event_id} should trigger cooldown for high-impact events"""
        response = requests.post(
            f"{BASE_URL}/api/events/trigger/eia_inventory",
            params={"actual": "-3.0M", "direction": "bullish"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["triggered"] == True
        assert "event" in data
        assert data["event"]["actual"] == "-3.0M"
        assert data["event"]["direction_bias"] == "bullish"
        
        # Check cooldown was activated
        state_response = requests.get(f"{BASE_URL}/api/events/state")
        state = state_response.json()
        assert state["cooldown_active"] == True
        
        print(f"✓ Event Trigger: triggered={data['triggered']}, cooldown_min={data.get('cooldown_minutes', 15)}")


class TestRiskControlCenter:
    """Tests for Risk Control Center - multi-layered risk management"""
    
    def test_risk_control_status_returns_full_status(self):
        """GET /api/risk-control/status should return level, rules, equity, pnl, cooldown"""
        response = requests.get(f"{BASE_URL}/api/risk-control/status")
        assert response.status_code == 200
        
        data = response.json()
        # Required fields
        assert "level" in data
        assert "rules" in data
        assert "equity" in data
        assert "today_pnl" in data
        assert "cooldown" in data
        assert "consecutive_losses" in data
        
        # Level should be one of: normal, reduced, degraded, halted
        assert data["level"] in ["normal", "reduced", "degraded", "halted"]
        
        # Should have 5 rules
        assert len(data["rules"]) == 5
        
        # Equity should have current, peak, drawdown_pct
        assert "current" in data["equity"]
        assert "peak" in data["equity"]
        assert "drawdown_pct" in data["equity"]
        
        print(f"✓ Risk Control Status: level={data['level']}, equity=${data['equity']['current']:.2f}")
    
    def test_risk_rules_evaluation(self):
        """GET /api/risk-control/rules should evaluate all 5 rules"""
        response = requests.get(f"{BASE_URL}/api/risk-control/rules")
        assert response.status_code == 200
        
        data = response.json()
        assert "level" in data
        assert "rules" in data
        assert "can_trade" in data
        assert "size_multiplier" in data
        
        # Should have 5 rules
        rules = data["rules"]
        assert len(rules) == 5
        
        # Each rule should have required fields
        for rule in rules:
            assert "name" in rule
            assert "enabled" in rule
            assert "threshold" in rule
            assert "current_value" in rule
            assert "triggered" in rule
            assert "action" in rule
        
        print(f"✓ Risk Rules: {len(rules)} rules, can_trade={data['can_trade']}")
    
    def test_exit_tiers_returns_4_tiers(self):
        """GET /api/risk-control/exit-tiers should return 4 tiers (WARNING, PRE_REDUCE, MAIN_STOP, DISASTER)"""
        response = requests.get(
            f"{BASE_URL}/api/risk-control/exit-tiers",
            params={"entry_price": 70, "direction": "long", "max_loss": 2}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "entry_price" in data
        assert "direction" in data
        assert "tiers" in data
        
        # Should have 4 tiers
        tiers = data["tiers"]
        assert len(tiers) == 4
        
        # Check tier names
        tier_names = [t["tier"] for t in tiers]
        assert "warning" in tier_names
        assert "pre_reduce" in tier_names
        assert "main_stop" in tier_names
        assert "disaster" in tier_names
        
        # Each tier should have exit_price and action
        for tier in tiers:
            assert "exit_price" in tier
            assert "action" in tier
            assert "loss_amount" in tier
        
        print(f"✓ Exit Tiers: {len(tiers)} tiers for entry=${data['entry_price']}")
    
    def test_daily_pnl_history(self):
        """GET /api/risk-control/daily-pnl should return history array"""
        response = requests.get(f"{BASE_URL}/api/risk-control/daily-pnl")
        assert response.status_code == 200
        
        data = response.json()
        assert "history" in data
        assert isinstance(data["history"], list)
        
        # If there's history, check structure
        if len(data["history"]) > 0:
            day = data["history"][0]
            assert "date" in day
            assert "realized_pnl" in day
            assert "total_pnl" in day
        
        print(f"✓ Daily PnL: {len(data['history'])} days of history")
    
    def test_slippage_stats(self):
        """GET /api/risk-control/slippage should return count, avg_ticks, max_ticks"""
        response = requests.get(f"{BASE_URL}/api/risk-control/slippage")
        assert response.status_code == 200
        
        data = response.json()
        assert "count" in data
        assert "avg_ticks" in data
        assert "max_ticks" in data
        
        print(f"✓ Slippage Stats: count={data['count']}, avg={data['avg_ticks']}")


class TestExecutionGate:
    """Tests for Execution Gate - pre-trade confirmation checklist"""
    
    def test_execution_gate_returns_8_checks(self):
        """GET /api/execution-gate/{symbol} should return gate_status and 8 checks"""
        response = requests.get(f"{BASE_URL}/api/execution-gate/CL")
        assert response.status_code == 200
        
        data = response.json()
        # Required fields
        assert "gate_status" in data
        assert "message" in data
        assert "can_enter" in data
        assert "checks" in data
        
        # Gate status should be one of: OPEN, CAUTION, PARTIAL, CLOSED
        assert data["gate_status"] in ["OPEN", "CAUTION", "PARTIAL", "CLOSED"]
        
        # Should have 8 checks
        assert len(data["checks"]) == 8
        
        # Each check should have status (pass/warn/fail)
        for check in data["checks"]:
            assert "name" in check
            assert "status" in check
            assert check["status"] in ["pass", "warn", "fail"]
            assert "value" in check
            assert "threshold" in check
        
        print(f"✓ Execution Gate: status={data['gate_status']}, {data['pass_count']}/{data['total_checks']} pass")


class TestSignalScorer:
    """Tests for Signal Scoring System - unified bullish/bearish scoring"""
    
    def test_signal_score_cl(self):
        """GET /api/signal-score/CL should return score, direction, zone, components"""
        response = requests.get(f"{BASE_URL}/api/signal-score/CL")
        assert response.status_code == 200
        
        data = response.json()
        # Required fields
        assert "score" in data
        assert "direction" in data
        assert "zone" in data
        assert "components" in data
        assert "bullish_pct" in data
        assert "bearish_pct" in data
        
        # Score should be -100 to 100
        assert -100 <= data["score"] <= 100
        
        # Direction should be one of: strong_long, long, neutral, short, strong_short
        assert data["direction"] in ["strong_long", "long", "neutral", "short", "strong_short"]
        
        # Components should have 8 factors
        components = data["components"]
        assert len(components) == 8
        
        # Bullish + bearish should roughly equal 100
        assert 99 <= data["bullish_pct"] + data["bearish_pct"] <= 101
        
        print(f"✓ Signal Score CL: score={data['score']:.1f}, direction={data['direction']}")
    
    def test_signal_score_bz(self):
        """GET /api/signal-score/BZ should return same structure for Brent"""
        response = requests.get(f"{BASE_URL}/api/signal-score/BZ")
        assert response.status_code == 200
        
        data = response.json()
        assert "score" in data
        assert "direction" in data
        assert "components" in data
        
        print(f"✓ Signal Score BZ: score={data['score']:.1f}, direction={data['direction']}")
    
    def test_signal_score_ng(self):
        """GET /api/signal-score/NG should return same structure for Natural Gas"""
        response = requests.get(f"{BASE_URL}/api/signal-score/NG")
        assert response.status_code == 200
        
        data = response.json()
        assert "score" in data
        assert "direction" in data
        assert "components" in data
        
        print(f"✓ Signal Score NG: score={data['score']:.1f}, direction={data['direction']}")


class TestExistingEndpoints:
    """Verify existing endpoints still work after new feature integration"""
    
    def test_system_status(self):
        """GET /api/system/status should still work"""
        response = requests.get(f"{BASE_URL}/api/system/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "is_running" in data
        assert "current_symbol" in data
        assert "equity" in data
        
        print(f"✓ System Status: running={data['is_running']}, symbol={data['current_symbol']}")
    
    def test_options_chain(self):
        """GET /api/options/chain/CL should still work"""
        response = requests.get(f"{BASE_URL}/api/options/chain/CL?expiry_days=30")
        assert response.status_code == 200
        
        data = response.json()
        assert "symbol" in data
        assert "underlying_price" in data
        assert "options" in data
        assert len(data["options"]) > 0
        
        print(f"✓ Options Chain: {len(data['options'])} options for CL")
    
    def test_notifications(self):
        """GET /api/notifications should still work"""
        response = requests.get(f"{BASE_URL}/api/notifications?limit=10")
        assert response.status_code == 200
        
        data = response.json()
        assert "notifications" in data
        assert "unread_count" in data
        
        print(f"✓ Notifications: {len(data['notifications'])} notifications, {data['unread_count']} unread")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
