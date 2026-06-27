"""
WTI Trading Platform - Iteration 9 Tests
Tests for: Strategy Simulation in Replay Engine, Modular Router Refactoring
New feature: POST /api/replay/simulate - simulate bot strategy on historical events
Backend refactored from monolithic server.py (2155 lines) into 6 modular routers
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# ─────────────────────────────────────────
# Root & System Endpoints (system.py router)
# ─────────────────────────────────────────

class TestRootAndSystem:
    """Test root and system endpoints after refactoring"""
    
    def test_root_endpoint_version(self):
        """GET /api/ - returns version 2.0.0"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        
        assert "version" in data
        assert data["version"] == "2.0.0", f"Expected version 2.0.0, got {data['version']}"
        assert "message" in data
        
        print(f"✓ Root endpoint: version={data['version']}")
    
    def test_system_status(self):
        """GET /api/system/status - returns running status and current_symbol"""
        response = requests.get(f"{BASE_URL}/api/system/status")
        assert response.status_code == 200
        data = response.json()
        
        assert "is_running" in data
        assert "current_symbol" in data
        assert "current_regime" in data
        assert "equity" in data
        assert "available_assets" in data
        
        # Verify available assets
        assert "CL" in data["available_assets"]
        assert "BZ" in data["available_assets"]
        assert "NG" in data["available_assets"]
        
        print(f"✓ System status: running={data['is_running']}, symbol={data['current_symbol']}, regime={data['current_regime']}")


# ─────────────────────────────────────────
# Auth Endpoints (auth.py router)
# ─────────────────────────────────────────

class TestAuthRouter:
    """Test auth endpoints after refactoring"""
    
    def test_login_with_admin_credentials(self):
        """POST /api/auth/login - login with admin credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@wti-trading.com", "password": "Admin@2026!"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "id" in data
        assert "email" in data
        assert data["email"] == "admin@wti-trading.com"
        assert "role" in data
        assert data["role"] == "admin"
        
        print(f"✓ Admin login successful: email={data['email']}, role={data['role']}")
    
    def test_login_invalid_credentials(self):
        """POST /api/auth/login - invalid credentials returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "wrong@email.com", "password": "wrongpassword"}
        )
        assert response.status_code == 401
        print("✓ Invalid login returns 401")


# ─────────────────────────────────────────
# Bot Endpoints (bot.py router)
# ─────────────────────────────────────────

class TestBotRouter:
    """Test bot endpoints after refactoring"""
    
    def test_bot_status(self):
        """GET /api/bot/status - returns bot status"""
        response = requests.get(f"{BASE_URL}/api/bot/status")
        assert response.status_code == 200
        data = response.json()
        
        assert "enabled" in data
        assert "min_confidence" in data
        assert "scan_interval_sec" in data
        assert "max_daily_trades" in data
        assert "pending_count" in data
        assert "executed_today" in data
        
        print(f"✓ Bot status: enabled={data['enabled']}, min_confidence={data['min_confidence']}")
    
    def test_bot_opportunities(self):
        """GET /api/bot/opportunities - returns pending opportunities"""
        response = requests.get(f"{BASE_URL}/api/bot/opportunities")
        assert response.status_code == 200
        data = response.json()
        
        assert "opportunities" in data
        assert isinstance(data["opportunities"], list)
        
        print(f"✓ Bot opportunities: {len(data['opportunities'])} pending")
    
    def test_bot_history(self):
        """GET /api/bot/history - returns opportunity history"""
        response = requests.get(f"{BASE_URL}/api/bot/history?limit=10")
        assert response.status_code == 200
        data = response.json()
        
        assert "history" in data
        assert isinstance(data["history"], list)
        
        print(f"✓ Bot history: {len(data['history'])} records")


# ─────────────────────────────────────────
# Analytics Endpoints (analytics.py router)
# ─────────────────────────────────────────

class TestAnalyticsRouter:
    """Test analytics endpoints after refactoring"""
    
    def test_fragility_endpoint(self):
        """GET /api/fragility - returns fragility data"""
        response = requests.get(f"{BASE_URL}/api/fragility")
        assert response.status_code == 200
        data = response.json()
        
        assert "score" in data
        assert "level" in data
        assert "size_multiplier" in data
        assert "should_halt" in data
        assert "should_reduce" in data
        
        print(f"✓ Fragility: score={data['score']}, level={data['level']}")
    
    def test_signal_score_endpoint(self):
        """GET /api/signal-score/CL - returns signal score data"""
        response = requests.get(f"{BASE_URL}/api/signal-score/CL")
        assert response.status_code == 200
        data = response.json()
        
        assert "bullish_pct" in data
        assert "bearish_pct" in data
        assert "direction" in data
        assert "components" in data  # API returns 'components' not 'factors'
        
        print(f"✓ Signal score CL: bullish={data['bullish_pct']}%, direction={data['direction']}")
    
    def test_risk_control_status(self):
        """GET /api/risk-control/status - returns risk control data"""
        response = requests.get(f"{BASE_URL}/api/risk-control/status")
        assert response.status_code == 200
        data = response.json()
        
        assert "can_trade" in data
        assert "equity" in data
        assert "consecutive_losses" in data
        
        print(f"✓ Risk control: can_trade={data['can_trade']}")
    
    def test_execution_gate_endpoint(self):
        """GET /api/execution-gate/CL - returns gate evaluation"""
        response = requests.get(f"{BASE_URL}/api/execution-gate/CL")
        assert response.status_code == 200
        data = response.json()
        
        assert "gate_status" in data  # API returns 'gate_status' not 'status'
        assert "can_enter" in data    # API returns 'can_enter' not 'can_execute'
        assert "checks" in data
        
        print(f"✓ Execution gate CL: status={data['gate_status']}, can_enter={data['can_enter']}")
    
    def test_events_calendar(self):
        """GET /api/events/calendar - returns event calendar"""
        response = requests.get(f"{BASE_URL}/api/events/calendar?hours_ahead=48")
        assert response.status_code == 200
        data = response.json()
        
        assert "events" in data
        assert "state" in data
        
        print(f"✓ Events calendar: {len(data['events'])} events")


# ─────────────────────────────────────────
# Options Endpoints (options.py router)
# ─────────────────────────────────────────

class TestOptionsRouter:
    """Test options endpoints after refactoring"""
    
    def test_options_chain(self):
        """GET /api/options/chain/CL - returns option chain"""
        response = requests.get(f"{BASE_URL}/api/options/chain/CL?expiry_days=30")
        assert response.status_code == 200
        data = response.json()
        
        assert "symbol" in data
        assert data["symbol"] == "CL"
        assert "underlying_price" in data
        assert "options" in data
        assert isinstance(data["options"], list)
        assert len(data["options"]) > 0
        
        # Verify option structure
        opt = data["options"][0]
        assert "type" in opt
        assert "strike" in opt
        assert "premium" in opt
        assert "delta" in opt
        assert "gamma" in opt
        assert "theta" in opt
        assert "vega" in opt
        
        print(f"✓ Options chain CL: {len(data['options'])} options, underlying=${data['underlying_price']}")
    
    def test_options_payoff_straddle(self):
        """GET /api/options/payoff/straddle - returns payoff diagram data"""
        response = requests.get(f"{BASE_URL}/api/options/payoff/straddle?symbol=CL&expiry_days=30")
        assert response.status_code == 200
        data = response.json()
        
        assert data["strategy"] == "straddle"
        assert "data" in data
        assert "max_profit" in data
        assert "max_loss" in data
        assert "breakeven_points" in data
        
        print(f"✓ Straddle payoff: max_profit={data['max_profit']}, max_loss={data['max_loss']}")


# ─────────────────────────────────────────
# Replay Endpoints (replay.py router) - NEW FEATURE
# ─────────────────────────────────────────

class TestReplayRouter:
    """Test replay endpoints including new simulate_strategy feature"""
    
    def test_get_replay_events(self):
        """GET /api/replay/events - returns list of historical events"""
        response = requests.get(f"{BASE_URL}/api/replay/events")
        assert response.status_code == 200
        data = response.json()
        
        assert "events" in data
        events = data["events"]
        assert isinstance(events, list)
        assert len(events) == 8, f"Expected 8 events, got {len(events)}"
        
        # Verify all expected events exist
        event_ids = [e["id"] for e in events]
        expected_ids = ["hormuz_2024", "opec_cut_2023", "svb_2023", "russia_ukraine_2022",
                       "covid_crash_2020", "eia_surprise_draw", "fed_hawkish_2024", "china_stimulus_2024"]
        for eid in expected_ids:
            assert eid in event_ids, f"Missing event: {eid}"
        
        print(f"✓ Replay events: {len(events)} historical events available")
    
    def test_replay_single_event(self):
        """GET /api/replay/{event_id} - returns replay bars and analytics"""
        response = requests.get(f"{BASE_URL}/api/replay/hormuz_2024")
        assert response.status_code == 200
        data = response.json()
        
        assert "event" in data
        assert "bars" in data
        assert "analytics" in data
        
        # Verify event structure
        event = data["event"]
        assert event["id"] == "hormuz_2024"
        assert "name" in event
        assert "description" in event
        assert "date" in event
        assert "trajectory" in event
        
        # Verify bars
        bars = data["bars"]
        assert len(bars) > 0
        bar = bars[0]
        assert "bar" in bar
        assert "price" in bar
        assert "regime" in bar
        assert "fragility_score" in bar
        
        # Verify analytics
        analytics = data["analytics"]
        assert "initial_price" in analytics
        assert "final_price" in analytics
        assert "total_return_pct" in analytics
        assert "max_drawdown_pct" in analytics
        assert "regime_distribution" in analytics
        
        print(f"✓ Replay hormuz_2024: {len(bars)} bars, return={analytics['total_return_pct']:.2f}%")
    
    def test_replay_invalid_event(self):
        """GET /api/replay/{invalid_id} - returns 404"""
        response = requests.get(f"{BASE_URL}/api/replay/nonexistent_event")
        assert response.status_code == 404
        print("✓ Invalid replay event returns 404")
    
    def test_simulate_strategy_basic(self):
        """POST /api/replay/simulate - simulate bot strategy on historical event"""
        response = requests.post(
            f"{BASE_URL}/api/replay/simulate",
            json={"event_id": "hormuz_2024", "config": {"min_confidence": 65}}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "event" in data
        assert "config" in data
        assert "trades" in data
        assert "equity_curve" in data
        assert "summary" in data
        
        # Verify event info
        event = data["event"]
        assert event["id"] == "hormuz_2024"
        assert "name" in event
        
        # Verify config
        config = data["config"]
        assert "min_confidence" in config
        assert config["min_confidence"] == 65
        
        # Verify trades structure
        trades = data["trades"]
        assert isinstance(trades, list)
        
        # Verify equity curve
        equity_curve = data["equity_curve"]
        assert isinstance(equity_curve, list)
        assert len(equity_curve) > 0
        ec_point = equity_curve[0]
        assert "bar" in ec_point
        assert "equity" in ec_point
        assert "drawdown_pct" in ec_point
        
        # Verify summary
        summary = data["summary"]
        assert "total_trades" in summary
        assert "winning_trades" in summary
        assert "losing_trades" in summary
        assert "win_rate" in summary
        assert "total_pnl" in summary
        assert "max_win" in summary
        assert "max_loss" in summary
        assert "final_equity" in summary
        assert "return_pct" in summary
        assert "max_drawdown_pct" in summary
        assert "profit_factor" in summary
        
        print(f"✓ Simulate hormuz_2024: {summary['total_trades']} trades, PnL=${summary['total_pnl']}, return={summary['return_pct']}%")
    
    def test_simulate_strategy_with_custom_config(self):
        """POST /api/replay/simulate - with custom SL/TP config"""
        response = requests.post(
            f"{BASE_URL}/api/replay/simulate",
            json={
                "event_id": "russia_ukraine_2022",
                "config": {
                    "min_confidence": 60,
                    "atr_sl_mult": 2.0,
                    "atr_tp1_mult": 2.5,
                    "atr_tp2_mult": 4.0
                }
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify config was applied
        config = data["config"]
        assert config["min_confidence"] == 60
        assert config["atr_sl_mult"] == 2.0
        assert config["atr_tp1_mult"] == 2.5
        assert config["atr_tp2_mult"] == 4.0
        
        summary = data["summary"]
        print(f"✓ Simulate russia_ukraine_2022 (custom config): {summary['total_trades']} trades, PnL=${summary['total_pnl']}")
    
    def test_simulate_strategy_covid_crash(self):
        """POST /api/replay/simulate - simulate on COVID crash (mega_crash trajectory)"""
        response = requests.post(
            f"{BASE_URL}/api/replay/simulate",
            json={"event_id": "covid_crash_2020", "config": {"min_confidence": 70}}
        )
        assert response.status_code == 200
        data = response.json()
        
        summary = data["summary"]
        assert "total_trades" in summary
        assert "max_drawdown_pct" in summary
        
        # COVID crash should have significant drawdown
        print(f"✓ Simulate covid_crash_2020: {summary['total_trades']} trades, max_dd={summary['max_drawdown_pct']}%")
    
    def test_simulate_strategy_invalid_event(self):
        """POST /api/replay/simulate - invalid event returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/replay/simulate",
            json={"event_id": "nonexistent_event", "config": {}}
        )
        assert response.status_code == 404
        print("✓ Simulate invalid event returns 404")
    
    def test_simulate_strategy_missing_event_id(self):
        """POST /api/replay/simulate - missing event_id returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/replay/simulate",
            json={"config": {"min_confidence": 65}}
        )
        assert response.status_code == 400
        print("✓ Simulate without event_id returns 400")
    
    def test_simulate_trade_structure(self):
        """POST /api/replay/simulate - verify trade structure has all required fields"""
        response = requests.post(
            f"{BASE_URL}/api/replay/simulate",
            json={"event_id": "opec_cut_2023", "config": {"min_confidence": 50}}  # Lower confidence to get trades
        )
        assert response.status_code == 200
        data = response.json()
        
        trades = data["trades"]
        if len(trades) > 0:
            trade = trades[0]
            # Verify trade structure
            assert "id" in trade
            assert "direction" in trade
            assert trade["direction"] in ["long", "short"]
            assert "entry_bar" in trade
            assert "entry_price" in trade
            assert "stop_loss" in trade
            assert "take_profit_1" in trade
            assert "take_profit_2" in trade
            assert "size" in trade
            assert "confidence" in trade
            assert "signal_score" in trade
            assert "regime_at_entry" in trade
            assert "fragility_at_entry" in trade
            assert "tp1_hit" in trade
            assert "partial_closes" in trade
            assert "exit_bar" in trade
            assert "exit_price" in trade
            assert "exit_reason" in trade
            assert "total_pnl" in trade
            
            print(f"✓ Trade structure verified: {trade['direction']} @ ${trade['entry_price']}, exit={trade['exit_reason']}, PnL=${trade['total_pnl']}")
        else:
            print("✓ No trades generated (market conditions may not have triggered signals)")


# ─────────────────────────────────────────
# Notifications Endpoint (system.py router)
# ─────────────────────────────────────────

class TestNotifications:
    """Test notifications endpoint"""
    
    def test_get_notifications(self):
        """GET /api/notifications - returns notifications list"""
        response = requests.get(f"{BASE_URL}/api/notifications")
        assert response.status_code == 200
        data = response.json()
        
        assert "notifications" in data
        assert "unread_count" in data
        assert isinstance(data["notifications"], list)
        
        print(f"✓ Notifications: {len(data['notifications'])} total, {data['unread_count']} unread")


# ─────────────────────────────────────────
# Additional System Endpoints
# ─────────────────────────────────────────

class TestAdditionalEndpoints:
    """Test additional endpoints to ensure refactoring didn't break anything"""
    
    def test_positions_endpoint(self):
        """GET /api/positions - returns open positions"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Positions: {len(data)} open positions")
    
    def test_trades_endpoint(self):
        """GET /api/trades - returns trade history"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Trades: {len(data)} trade records")
    
    def test_market_current(self):
        """GET /api/market/current - returns current market data"""
        response = requests.get(f"{BASE_URL}/api/market/current")
        assert response.status_code == 200
        data = response.json()
        
        assert "symbol" in data
        assert "price" in data
        assert "bid" in data
        assert "ask" in data
        assert "indicators" in data
        
        print(f"✓ Market current: {data['symbol']} @ ${data['price']}")
    
    def test_assets_endpoint(self):
        """GET /api/assets - returns available assets"""
        response = requests.get(f"{BASE_URL}/api/assets")
        assert response.status_code == 200
        data = response.json()
        
        # API returns list of asset objects
        assert isinstance(data, list)
        assert len(data) >= 3
        
        # Verify asset structure
        symbols = [asset.get("symbol") for asset in data]
        assert "CL" in symbols
        assert "BZ" in symbols
        assert "NG" in symbols
        
        print(f"✓ Assets: {symbols}")
    
    def test_regime_current(self):
        """GET /api/regime/current - returns current regime"""
        response = requests.get(f"{BASE_URL}/api/regime/current")
        assert response.status_code == 200
        data = response.json()
        
        assert "current_regime" in data  # API returns 'current_regime' not 'current'
        assert "auto_regime" in data
        
        print(f"✓ Regime: {data['current_regime']}")
    
    def test_pnl_realtime(self):
        """GET /api/pnl/realtime - returns realtime PnL"""
        response = requests.get(f"{BASE_URL}/api/pnl/realtime")
        assert response.status_code == 200
        data = response.json()
        
        assert "equity" in data
        assert "realized_pnl_today" in data
        assert "unrealized_pnl" in data
        
        print(f"✓ PnL realtime: equity=${data['equity']}, realized=${data['realized_pnl_today']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
