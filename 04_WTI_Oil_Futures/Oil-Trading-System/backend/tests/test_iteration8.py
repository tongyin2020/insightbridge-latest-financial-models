"""
WTI Trading Platform - Iteration 8 Tests
Tests for: Strategy Replay, Options P&L Payoff Diagrams, Tiered Take-Profit, Regime Notifications
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestReplayEvents:
    """Test Strategy Replay endpoints - 8 historical events"""
    
    def test_get_replay_events_list(self):
        """GET /api/replay/events - returns 8 historical events"""
        response = requests.get(f"{BASE_URL}/api/replay/events")
        assert response.status_code == 200
        data = response.json()
        
        # Should have 'events' key with list
        assert "events" in data
        events = data["events"]
        assert isinstance(events, list)
        assert len(events) == 8, f"Expected 8 events, got {len(events)}"
        
        # Verify event structure
        expected_event_ids = [
            "hormuz_2024", "opec_cut_2023", "svb_2023", "russia_ukraine_2022",
            "covid_crash_2020", "eia_surprise_draw", "fed_hawkish_2024", "china_stimulus_2024"
        ]
        actual_ids = [e["id"] for e in events]
        for eid in expected_event_ids:
            assert eid in actual_ids, f"Missing event: {eid}"
        
        # Verify event fields
        for event in events:
            assert "id" in event
            assert "name" in event
            assert "description" in event
            assert "date" in event
            assert "initial_price" in event
            assert "max_move_pct" in event
            assert "duration_bars" in event
            assert "trajectory" in event
        
        print(f"✓ Replay events list: {len(events)} events returned")
    
    def test_replay_hormuz_2024(self):
        """GET /api/replay/hormuz_2024 - returns bars[], analytics{}, event{}"""
        response = requests.get(f"{BASE_URL}/api/replay/hormuz_2024")
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "event" in data
        assert "bars" in data
        assert "analytics" in data
        
        # Verify event info
        event = data["event"]
        assert event["id"] == "hormuz_2024"
        assert "Hormuz" in event["name"]
        
        # Verify bars
        bars = data["bars"]
        assert isinstance(bars, list)
        assert len(bars) > 0
        
        # Verify bar structure
        bar = bars[0]
        assert "bar" in bar
        assert "price" in bar
        assert "change_pct" in bar
        assert "regime" in bar
        assert "fragility_score" in bar
        
        # Verify analytics
        analytics = data["analytics"]
        assert "initial_price" in analytics
        assert "final_price" in analytics
        assert "max_price" in analytics
        assert "min_price" in analytics
        assert "total_return_pct" in analytics
        assert "max_drawdown_pct" in analytics
        assert "avg_fragility" in analytics
        assert "regime_distribution" in analytics
        
        print(f"✓ Hormuz 2024 replay: {len(bars)} bars, return {analytics['total_return_pct']:.2f}%")
    
    def test_replay_covid_crash_2020(self):
        """GET /api/replay/covid_crash_2020 - returns mega crash trajectory"""
        response = requests.get(f"{BASE_URL}/api/replay/covid_crash_2020")
        assert response.status_code == 200
        data = response.json()
        
        assert "bars" in data
        bars = data["bars"]
        assert len(bars) > 0
        
        # COVID crash should have negative return
        analytics = data["analytics"]
        assert analytics["total_return_pct"] < 0, "COVID crash should have negative return"
        assert analytics["max_drawdown_pct"] > 0, "Should have significant drawdown"
        
        # Verify trajectory type
        event = data["event"]
        assert event["trajectory"] == "mega_crash"
        
        print(f"✓ COVID crash replay: {len(bars)} bars, return {analytics['total_return_pct']:.2f}%, drawdown {analytics['max_drawdown_pct']:.2f}%")
    
    def test_replay_russia_ukraine_2022(self):
        """GET /api/replay/russia_ukraine_2022 - returns mega spike event"""
        response = requests.get(f"{BASE_URL}/api/replay/russia_ukraine_2022")
        assert response.status_code == 200
        data = response.json()
        
        assert "bars" in data
        bars = data["bars"]
        assert len(bars) > 0
        
        # Russia-Ukraine should have positive return (oil spike)
        analytics = data["analytics"]
        assert analytics["total_return_pct"] > 0, "Russia-Ukraine should have positive return (oil spike)"
        
        # Verify trajectory type
        event = data["event"]
        assert event["trajectory"] == "mega_spike"
        
        print(f"✓ Russia-Ukraine replay: {len(bars)} bars, return {analytics['total_return_pct']:.2f}%")
    
    def test_replay_invalid_event(self):
        """GET /api/replay/invalid_event - returns 404"""
        response = requests.get(f"{BASE_URL}/api/replay/invalid_event_xyz")
        assert response.status_code == 404
        print("✓ Invalid event returns 404")


class TestOptionsPayoff:
    """Test Options P&L Payoff Diagram endpoints - 6 strategies"""
    
    def test_payoff_straddle(self):
        """GET /api/options/payoff/straddle - returns data[], max_profit, max_loss, breakeven_points"""
        response = requests.get(f"{BASE_URL}/api/options/payoff/straddle?symbol=CL&expiry_days=30")
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "strategy" in data
        assert data["strategy"] == "straddle"
        assert "name" in data
        assert "spot_price" in data
        assert "strike" in data
        assert "cost" in data
        assert "max_profit" in data
        assert "max_loss" in data
        assert "breakeven_points" in data
        assert "data" in data
        
        # Verify data points
        payoff_data = data["data"]
        assert isinstance(payoff_data, list)
        assert len(payoff_data) > 0
        
        # Verify data point structure
        point = payoff_data[0]
        assert "price" in point
        assert "expiry_pnl" in point
        assert "current_pnl" in point
        
        # Straddle should have 2 breakeven points
        assert len(data["breakeven_points"]) == 2
        
        print(f"✓ Straddle payoff: {len(payoff_data)} points, max_profit=${data['max_profit']}, max_loss=${data['max_loss']}")
    
    def test_payoff_iron_condor(self):
        """GET /api/options/payoff/iron_condor - returns payoff data"""
        response = requests.get(f"{BASE_URL}/api/options/payoff/iron_condor?symbol=CL&expiry_days=30")
        assert response.status_code == 200
        data = response.json()
        
        assert data["strategy"] == "iron_condor"
        assert "data" in data
        assert len(data["data"]) > 0
        assert "max_profit" in data
        assert "max_loss" in data
        assert "breakeven_points" in data
        
        print(f"✓ Iron Condor payoff: max_profit=${data['max_profit']}, max_loss=${data['max_loss']}")
    
    def test_payoff_butterfly(self):
        """GET /api/options/payoff/butterfly - returns payoff data"""
        response = requests.get(f"{BASE_URL}/api/options/payoff/butterfly?symbol=CL&expiry_days=30")
        assert response.status_code == 200
        data = response.json()
        
        assert data["strategy"] == "butterfly"
        assert "data" in data
        assert len(data["data"]) > 0
        assert "max_profit" in data
        assert "max_loss" in data
        
        print(f"✓ Butterfly payoff: max_profit=${data['max_profit']}, max_loss=${data['max_loss']}")
    
    def test_payoff_calendar_spread(self):
        """GET /api/options/payoff/calendar_spread - returns payoff data"""
        response = requests.get(f"{BASE_URL}/api/options/payoff/calendar_spread?symbol=CL&expiry_days=30")
        assert response.status_code == 200
        data = response.json()
        
        assert data["strategy"] == "calendar_spread"
        assert "data" in data
        assert len(data["data"]) > 0
        
        print(f"✓ Calendar Spread payoff: max_profit=${data['max_profit']}, max_loss=${data['max_loss']}")
    
    def test_payoff_ratio_spread(self):
        """GET /api/options/payoff/ratio_spread - returns payoff data"""
        response = requests.get(f"{BASE_URL}/api/options/payoff/ratio_spread?symbol=CL&expiry_days=30")
        assert response.status_code == 200
        data = response.json()
        
        assert data["strategy"] == "ratio_spread"
        assert "data" in data
        assert len(data["data"]) > 0
        
        print(f"✓ Ratio Spread payoff: max_profit=${data['max_profit']}, max_loss=${data['max_loss']}")
    
    def test_payoff_strangle(self):
        """GET /api/options/payoff/strangle - returns payoff data"""
        response = requests.get(f"{BASE_URL}/api/options/payoff/strangle?symbol=CL&expiry_days=30")
        assert response.status_code == 200
        data = response.json()
        
        assert data["strategy"] == "strangle"
        assert "data" in data
        assert len(data["data"]) > 0
        
        print(f"✓ Strangle payoff: max_profit=${data['max_profit']}, max_loss=${data['max_loss']}")
    
    def test_payoff_invalid_strategy(self):
        """GET /api/options/payoff/invalid - returns 400"""
        response = requests.get(f"{BASE_URL}/api/options/payoff/invalid_strategy?symbol=CL&expiry_days=30")
        assert response.status_code == 400
        print("✓ Invalid strategy returns 400")


class TestBotAndExistingEndpoints:
    """Test bot status and existing endpoints still work"""
    
    def test_bot_status(self):
        """GET /api/bot/status - returns bot status"""
        response = requests.get(f"{BASE_URL}/api/bot/status")
        assert response.status_code == 200
        data = response.json()
        
        assert "enabled" in data
        assert "min_confidence" in data
        assert "scan_interval_sec" in data
        assert "max_daily_trades" in data
        
        print(f"✓ Bot status: enabled={data['enabled']}, min_confidence={data['min_confidence']}")
    
    def test_bot_toggle(self):
        """POST /api/bot/toggle - toggles bot"""
        # Get current state
        status_res = requests.get(f"{BASE_URL}/api/bot/status")
        current_enabled = status_res.json()["enabled"]
        
        # Toggle
        response = requests.post(f"{BASE_URL}/api/bot/toggle?enabled=true")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        
        # Toggle back
        requests.post(f"{BASE_URL}/api/bot/toggle?enabled={str(current_enabled).lower()}")
        
        print(f"✓ Bot toggle works")
    
    def test_fragility_endpoint(self):
        """GET /api/fragility - returns fragility assessment"""
        response = requests.get(f"{BASE_URL}/api/fragility")
        assert response.status_code == 200
        data = response.json()
        
        assert "score" in data
        assert "level" in data
        assert "size_multiplier" in data
        
        print(f"✓ Fragility: score={data['score']}, level={data['level']}")
    
    def test_signal_score_endpoint(self):
        """GET /api/signal-score/CL - returns signal score"""
        response = requests.get(f"{BASE_URL}/api/signal-score/CL")
        assert response.status_code == 200
        data = response.json()
        
        assert "bullish_pct" in data
        assert "bearish_pct" in data
        assert "direction" in data
        
        print(f"✓ Signal score: bullish={data['bullish_pct']}%, bearish={data['bearish_pct']}%")
    
    def test_risk_control_status(self):
        """GET /api/risk-control/status - returns risk control status"""
        response = requests.get(f"{BASE_URL}/api/risk-control/status")
        assert response.status_code == 200
        data = response.json()
        
        assert "can_trade" in data
        assert "equity" in data
        assert "current" in data["equity"]
        
        print(f"✓ Risk control: can_trade={data['can_trade']}, equity=${data['equity']['current']}")
    
    def test_notifications_endpoint(self):
        """GET /api/notifications - returns notifications with unread count"""
        response = requests.get(f"{BASE_URL}/api/notifications")
        assert response.status_code == 200
        data = response.json()
        
        assert "notifications" in data
        assert "unread_count" in data
        
        print(f"✓ Notifications: {len(data['notifications'])} notifications, {data['unread_count']} unread")


class TestTakeProfitTracking:
    """Test tiered take-profit tracking in bot"""
    
    def test_bot_opportunities_have_tp_levels(self):
        """Bot opportunities should have take_profit_1 and take_profit_2"""
        # Enable bot first
        requests.post(f"{BASE_URL}/api/bot/toggle?enabled=true")
        
        # Wait a bit for scanner to run
        import time
        time.sleep(2)
        
        # Get opportunities
        response = requests.get(f"{BASE_URL}/api/bot/opportunities")
        assert response.status_code == 200
        data = response.json()
        
        opportunities = data.get("opportunities", [])
        
        # If there are opportunities, verify TP levels
        if opportunities:
            opp = opportunities[0]
            assert "take_profit_1" in opp, "Opportunity should have take_profit_1"
            assert "take_profit_2" in opp, "Opportunity should have take_profit_2"
            assert "stop_loss" in opp, "Opportunity should have stop_loss"
            print(f"✓ Opportunity has TP levels: TP1=${opp['take_profit_1']}, TP2=${opp['take_profit_2']}, SL=${opp['stop_loss']}")
        else:
            print("✓ No pending opportunities (bot may not have found signals yet)")
        
        # Disable bot
        requests.post(f"{BASE_URL}/api/bot/toggle?enabled=false")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
