"""
Iteration 12 Backend Tests - PvP Battle, Social Features, Mobile PWA
Tests for the final features: Strategy PvP battles, Social/Copy trading, and PWA manifest.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@wti-trading.com"
ADMIN_PASSWORD = "Admin@2026!"
TEST_EMAIL = "trader@test.com"
TEST_PASSWORD = "Test@123!"


class TestSystemHealth:
    """Basic system health checks"""
    
    def test_system_status(self):
        """GET /api/system/status returns running status"""
        response = requests.get(f"{BASE_URL}/api/system/status")
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        assert "current_symbol" in data
        assert "equity" in data
        print(f"✓ System status: mode={data['mode']}, symbol={data['current_symbol']}")


class TestAuth:
    """Authentication endpoint tests"""
    
    def test_login_admin(self):
        """POST /api/auth/login with admin credentials returns token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "email" in data
        assert data["email"] == ADMIN_EMAIL.lower()
        print(f"✓ Admin login successful: {data['email']}")
    
    def test_login_invalid_credentials(self):
        """POST /api/auth/login with invalid credentials returns 401"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "wrong@example.com",
            "password": "wrongpass"
        })
        assert response.status_code == 401
        print("✓ Invalid login correctly rejected")
    
    def test_register_new_user(self):
        """POST /api/auth/register creates new user"""
        import time
        unique_email = f"test_iter12_{int(time.time())}@test.com"
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "Test@123!",
            "name": "Test User Iter12"
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["email"] == unique_email.lower()
        print(f"✓ User registration successful: {data['email']}")


class TestPvPBattle:
    """Strategy PvP Battle endpoint tests - NEW in Iteration 12"""
    
    def test_pvp_battle_basic(self):
        """POST /api/social/pvp with two configs returns battle results"""
        config_a = {"min_confidence": 40, "atr_sl_mult": 1.0, "atr_tp1_mult": 1.5, "atr_tp2_mult": 3.0}
        config_b = {"min_confidence": 70, "atr_sl_mult": 2.0, "atr_tp1_mult": 2.5, "atr_tp2_mult": 4.0}
        
        response = requests.post(f"{BASE_URL}/api/social/pvp", json={
            "name_a": "Aggressive Strategy",
            "name_b": "Conservative Strategy",
            "config_a": config_a,
            "config_b": config_b
        })
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "id" in data
        assert data["id"].startswith("pvp_")
        assert "name_a" in data
        assert "name_b" in data
        assert "config_a" in data
        assert "config_b" in data
        assert "per_event" in data
        assert "summary_a" in data
        assert "summary_b" in data
        assert "overall_winner" in data
        assert "events_count" in data
        
        # Verify per_event breakdown
        assert len(data["per_event"]) > 0
        for event in data["per_event"]:
            assert "event_id" in event
            assert "event_name" in event
            assert "a_pnl" in event
            assert "b_pnl" in event
            assert "winner" in event
            assert event["winner"] in ["a", "b", "tie"]
        
        # Verify summary structure
        for summary_key in ["summary_a", "summary_b"]:
            summary = data[summary_key]
            assert "total_pnl" in summary
            assert "total_trades" in summary
            assert "win_rate" in summary
            assert "max_drawdown_pct" in summary
            assert "events_won" in summary
        
        assert data["overall_winner"] in ["a", "b", "tie"]
        print(f"✓ PvP Battle completed: {data['events_count']} events, winner={data['overall_winner']}")
        print(f"  Strategy A: PnL=${data['summary_a']['total_pnl']}, Win Rate={data['summary_a']['win_rate']}%")
        print(f"  Strategy B: PnL=${data['summary_b']['total_pnl']}, Win Rate={data['summary_b']['win_rate']}%")
    
    def test_pvp_battle_with_specific_events(self):
        """POST /api/social/pvp with specific event_ids works"""
        response = requests.post(f"{BASE_URL}/api/social/pvp", json={
            "name_a": "Test A",
            "name_b": "Test B",
            "config_a": {"min_confidence": 50, "atr_sl_mult": 1.5, "atr_tp1_mult": 2.0, "atr_tp2_mult": 3.5},
            "config_b": {"min_confidence": 60, "atr_sl_mult": 1.5, "atr_tp1_mult": 2.0, "atr_tp2_mult": 3.5},
            "event_ids": ["covid_crash_2020", "opec_cut_2023"]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["events_count"] == 2
        print(f"✓ PvP Battle with specific events: {data['events_count']} events tested")
    
    def test_pvp_battle_missing_config(self):
        """POST /api/social/pvp without configs returns 400"""
        response = requests.post(f"{BASE_URL}/api/social/pvp", json={
            "name_a": "Test A",
            "name_b": "Test B"
        })
        assert response.status_code == 400
        print("✓ PvP Battle correctly rejects missing configs")
    
    def test_pvp_history(self):
        """GET /api/social/pvp/history returns list of past battles"""
        response = requests.get(f"{BASE_URL}/api/social/pvp/history")
        assert response.status_code == 200
        data = response.json()
        assert "battles" in data
        assert isinstance(data["battles"], list)
        if len(data["battles"]) > 0:
            battle = data["battles"][0]
            assert "id" in battle
            assert "name_a" in battle
            assert "name_b" in battle
            assert "overall_winner" in battle
        print(f"✓ PvP History: {len(data['battles'])} battles found")


class TestSocialFeatures:
    """Social/Copy Trading endpoint tests"""
    
    def test_leaderboard(self):
        """GET /api/social/leaderboard returns ranked strategies"""
        response = requests.get(f"{BASE_URL}/api/social/leaderboard")
        assert response.status_code == 200
        data = response.json()
        assert "strategies" in data
        assert isinstance(data["strategies"], list)
        print(f"✓ Leaderboard: {len(data['strategies'])} strategies")
    
    def test_share_strategy(self):
        """POST /api/social/share creates and returns a shared strategy"""
        import time
        strategy_name = f"TEST_Strategy_{int(time.time())}"
        response = requests.post(f"{BASE_URL}/api/social/share", json={
            "name": strategy_name,
            "description": "Test strategy for iteration 12",
            "config": {"min_confidence": 55, "atr_sl_mult": 1.5, "atr_tp1_mult": 2.0, "atr_tp2_mult": 3.5},
            "performance": {"total_pnl": 1500, "total_trades": 25, "win_rate": 60, "score": 1200}
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["name"] == strategy_name
        assert "config" in data
        assert "performance" in data
        assert "author" in data
        assert "public" in data
        assert data["public"] == True
        print(f"✓ Strategy shared: {data['id']}")
        return data["id"]
    
    def test_follow_unfollow_strategy(self):
        """POST /api/social/follow/{strategy_id} toggles follow state"""
        # First create a strategy to follow
        import time
        strategy_name = f"TEST_FollowMe_{int(time.time())}"
        create_response = requests.post(f"{BASE_URL}/api/social/share", json={
            "name": strategy_name,
            "config": {"min_confidence": 50, "atr_sl_mult": 1.5, "atr_tp1_mult": 2.0, "atr_tp2_mult": 3.5},
            "performance": {"total_pnl": 1000, "score": 800}
        })
        assert create_response.status_code == 200
        strategy_id = create_response.json()["id"]
        
        # Follow the strategy
        follow_response = requests.post(f"{BASE_URL}/api/social/follow/{strategy_id}")
        assert follow_response.status_code == 200
        follow_data = follow_response.json()
        assert follow_data["action"] == "followed"
        assert follow_data["strategy_id"] == strategy_id
        assert "config" in follow_data
        print(f"✓ Strategy followed: {strategy_id}")
        
        # Unfollow the strategy
        unfollow_response = requests.post(f"{BASE_URL}/api/social/follow/{strategy_id}")
        assert unfollow_response.status_code == 200
        unfollow_data = unfollow_response.json()
        assert unfollow_data["action"] == "unfollowed"
        print(f"✓ Strategy unfollowed: {strategy_id}")
    
    def test_follow_nonexistent_strategy(self):
        """POST /api/social/follow/nonexistent returns 404"""
        response = requests.post(f"{BASE_URL}/api/social/follow/nonexistent_strategy_id")
        assert response.status_code == 404
        print("✓ Follow nonexistent strategy correctly returns 404")
    
    def test_my_strategies(self):
        """GET /api/social/my-strategies returns user's strategies"""
        response = requests.get(f"{BASE_URL}/api/social/my-strategies")
        assert response.status_code == 200
        data = response.json()
        assert "strategies" in data
        assert isinstance(data["strategies"], list)
        print(f"✓ My Strategies: {len(data['strategies'])} strategies")
    
    def test_following(self):
        """GET /api/social/following returns followed strategies"""
        response = requests.get(f"{BASE_URL}/api/social/following")
        assert response.status_code == 200
        data = response.json()
        assert "following" in data
        assert isinstance(data["following"], list)
        print(f"✓ Following: {len(data['following'])} strategies")


class TestStrategyOptimizer:
    """Strategy Optimizer endpoint tests"""
    
    def test_optimizer_default(self):
        """POST /api/replay/optimize with default params returns best config"""
        response = requests.post(f"{BASE_URL}/api/replay/optimize", json={})
        assert response.status_code == 200
        data = response.json()
        
        assert "best" in data
        assert "top_10" in data
        assert "total_combinations" in data
        assert "events_tested" in data
        
        # Verify best config structure
        best = data["best"]
        assert "config" in best
        assert "total_pnl" in best
        assert "total_trades" in best
        assert "win_rate" in best
        assert "score" in best
        
        # Verify config has required fields
        config = best["config"]
        assert "min_confidence" in config
        assert "atr_sl_mult" in config
        assert "atr_tp1_mult" in config
        assert "atr_tp2_mult" in config
        
        print(f"✓ Optimizer: {data['total_combinations']} combinations, {data['events_tested']} events")
        print(f"  Best config: conf={config['min_confidence']}%, SL={config['atr_sl_mult']}x, TP1={config['atr_tp1_mult']}x, TP2={config['atr_tp2_mult']}x")
        print(f"  Best score: {best['score']}, PnL=${best['total_pnl']}")


class TestReplayEndpoints:
    """Replay/Simulation endpoint tests"""
    
    def test_replay_events_list(self):
        """GET /api/replay/events returns list of historical events"""
        response = requests.get(f"{BASE_URL}/api/replay/events")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert len(data["events"]) > 0
        print(f"✓ Replay events: {len(data['events'])} events available")
    
    def test_replay_simulate(self):
        """POST /api/replay/simulate runs strategy simulation"""
        response = requests.post(f"{BASE_URL}/api/replay/simulate", json={
            "event_id": "covid_crash_2020",
            "config": {"min_confidence": 50, "atr_sl_mult": 1.5, "atr_tp1_mult": 2.0, "atr_tp2_mult": 3.5}
        })
        assert response.status_code == 200
        data = response.json()
        assert "event" in data
        assert "summary" in data
        assert "trades" in data
        print(f"✓ Replay simulate: {data['summary']['total_trades']} trades, PnL=${data['summary']['total_pnl']}")
    
    def test_replay_compare(self):
        """POST /api/replay/compare runs multi-event comparison"""
        response = requests.post(f"{BASE_URL}/api/replay/compare", json={
            "config": {"min_confidence": 55, "atr_sl_mult": 1.5, "atr_tp1_mult": 2.0, "atr_tp2_mult": 3.5}
        })
        assert response.status_code == 200
        data = response.json()
        assert "events_count" in data
        assert "per_event" in data
        assert "aggregate" in data
        print(f"✓ Replay compare: {data['events_count']} events, aggregate PnL=${data['aggregate']['total_pnl']}")


class TestOptionsEndpoints:
    """Options trading endpoint tests"""
    
    def test_options_chain(self):
        """GET /api/options/chain/CL returns options data"""
        response = requests.get(f"{BASE_URL}/api/options/chain/CL")
        assert response.status_code == 200
        data = response.json()
        assert "symbol" in data
        assert "underlying_price" in data
        assert "options" in data
        assert len(data["options"]) > 0
        print(f"✓ Options chain: {len(data['options'])} options for CL @ ${data['underlying_price']:.2f}")
    
    def test_options_straddle(self):
        """POST /api/options/strategy/straddle creates straddle"""
        response = requests.post(f"{BASE_URL}/api/options/strategy/straddle?symbol=CL")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "type" in data
        assert "legs" in data
        print(f"✓ Straddle strategy: {data['name']}")
    
    def test_options_strangle(self):
        """POST /api/options/strategy/strangle creates strangle"""
        response = requests.post(f"{BASE_URL}/api/options/strategy/strangle?symbol=CL")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "type" in data
        print(f"✓ Strangle strategy: {data['name']}")
    
    def test_options_iron_condor(self):
        """POST /api/options/strategy/iron-condor creates iron condor"""
        response = requests.post(f"{BASE_URL}/api/options/strategy/iron-condor?symbol=CL")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "legs" in data
        print(f"✓ Iron Condor strategy: {data['name']}")
    
    def test_options_butterfly(self):
        """POST /api/options/strategy/butterfly creates butterfly"""
        response = requests.post(f"{BASE_URL}/api/options/strategy/butterfly?symbol=CL")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "legs" in data
        print(f"✓ Butterfly strategy: {data['name']}")
    
    def test_options_backtest(self):
        """GET /api/options/backtest runs options backtest"""
        response = requests.post(f"{BASE_URL}/api/options/backtest?strategy_type=straddle&symbol=CL")
        assert response.status_code == 200
        data = response.json()
        assert "strategy_type" in data
        # Response may have num_simulations or avg_pnl_per_trade depending on implementation
        assert "num_simulations" in data or "avg_pnl_per_trade" in data
        print(f"✓ Options backtest: strategy_type={data['strategy_type']}")


class TestTradingBot:
    """Trading bot endpoint tests"""
    
    def test_bot_status(self):
        """GET /api/bot/status returns bot status"""
        response = requests.get(f"{BASE_URL}/api/bot/status")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "min_confidence" in data
        print(f"✓ Bot status: enabled={data['enabled']}, min_confidence={data['min_confidence']}%")
    
    def test_bot_opportunities(self):
        """GET /api/bot/opportunities returns pending opportunities"""
        response = requests.get(f"{BASE_URL}/api/bot/opportunities")
        assert response.status_code == 200
        data = response.json()
        assert "opportunities" in data
        print(f"✓ Bot opportunities: {len(data['opportunities'])} pending")


class TestExportsAlerts:
    """Trade export and price alerts endpoint tests"""
    
    def test_csv_export(self):
        """GET /api/trades/export/csv returns CSV data"""
        response = requests.get(f"{BASE_URL}/api/trades/export/csv")
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        print("✓ CSV export working")
    
    def test_get_alerts(self):
        """GET /api/alerts returns alerts list"""
        response = requests.get(f"{BASE_URL}/api/alerts")
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        print(f"✓ Alerts: {len(data['alerts'])} active")
    
    def test_create_alert(self):
        """POST /api/alerts creates price alert"""
        response = requests.post(f"{BASE_URL}/api/alerts", json={
            "symbol": "CL",
            "target_price": 80.0,
            "condition": "above",
            "note": "Test alert iter12"
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["symbol"] == "CL"
        assert data["target_price"] == 80.0
        print(f"✓ Alert created: {data['id']}")


class TestAnalytics:
    """Analytics endpoint tests"""
    
    def test_fragility(self):
        """GET /api/fragility returns fragility score"""
        response = requests.get(f"{BASE_URL}/api/fragility")
        assert response.status_code == 200
        data = response.json()
        assert "score" in data
        assert "level" in data
        print(f"✓ Fragility: score={data['score']}, level={data['level']}")
    
    def test_risk_control_status(self):
        """GET /api/risk-control/status returns risk status"""
        response = requests.get(f"{BASE_URL}/api/risk-control/status")
        assert response.status_code == 200
        data = response.json()
        assert "can_trade" in data
        print(f"✓ Risk control: can_trade={data['can_trade']}")


class TestPWAManifest:
    """PWA manifest accessibility test"""
    
    def test_manifest_accessible(self):
        """GET /manifest.json is accessible"""
        # The manifest is served by the frontend, not the backend API
        # We test the frontend URL directly
        frontend_url = BASE_URL.replace("/api", "")
        response = requests.get(f"{frontend_url}/manifest.json")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "short_name" in data
        assert "display" in data
        print(f"✓ PWA Manifest: {data['name']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
