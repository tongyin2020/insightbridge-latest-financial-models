"""
Iteration 11 Backend Tests
Tests for:
1. Strategy Optimizer (POST /api/replay/optimize)
2. Social/Copy Trading (POST /api/social/share, GET /api/social/leaderboard, POST /api/social/follow/{id}, GET /api/social/following)
3. Existing features regression
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://petro-trading-ai.preview.emergentagent.com').rstrip('/')

class TestStrategyOptimizer:
    """Tests for POST /api/replay/optimize - Grid search over parameter combinations"""
    
    def test_optimize_default_params(self):
        """Test optimizer with default parameters"""
        response = requests.post(f"{BASE_URL}/api/replay/optimize", json={})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "best" in data, "Response should contain 'best' config"
        assert "top_10" in data, "Response should contain 'top_10' list"
        assert "total_combinations" in data, "Response should contain 'total_combinations'"
        assert "events_tested" in data, "Response should contain 'events_tested'"
        
        # Verify best config structure
        best = data["best"]
        assert "config" in best, "Best should have 'config'"
        assert "total_pnl" in best, "Best should have 'total_pnl'"
        assert "total_trades" in best, "Best should have 'total_trades'"
        assert "win_rate" in best, "Best should have 'win_rate'"
        assert "score" in best, "Best should have 'score'"
        
        # Verify config parameters
        config = best["config"]
        assert "min_confidence" in config
        assert "atr_sl_mult" in config
        assert "atr_tp1_mult" in config
        assert "atr_tp2_mult" in config
        
        # Verify top_10 is a list with up to 10 items
        assert isinstance(data["top_10"], list)
        assert len(data["top_10"]) <= 10
        
        # Verify total_combinations is reasonable (should be ~108 with default ranges)
        assert data["total_combinations"] > 0
        print(f"Optimizer tested {data['total_combinations']} combinations across {data['events_tested']} events")
        print(f"Best config: {best['config']} with score {best['score']}")
    
    def test_optimize_custom_ranges(self):
        """Test optimizer with custom parameter ranges"""
        response = requests.post(f"{BASE_URL}/api/replay/optimize", json={
            "confidence_range": [50, 60],
            "sl_range": [1.5, 2.0],
            "tp1_range": [2.0],
            "tp2_range": [3.5, 4.0]
        })
        assert response.status_code == 200
        
        data = response.json()
        # With 2*2*1*2 = 8 combinations (minus invalid tp2<=tp1)
        assert data["total_combinations"] > 0
        assert data["total_combinations"] <= 8
        print(f"Custom ranges: {data['total_combinations']} combinations tested")
    
    def test_optimize_specific_events(self):
        """Test optimizer with specific event IDs"""
        response = requests.post(f"{BASE_URL}/api/replay/optimize", json={
            "event_ids": ["hormuz_2024", "opec_cut_2023"],
            "confidence_range": [50, 60],
            "sl_range": [1.5],
            "tp1_range": [2.0],
            "tp2_range": [3.5]
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["events_tested"] == 2
        print(f"Tested on 2 specific events: {data['events_tested']}")


class TestSocialCopyTrading:
    """Tests for Social/Copy Trading endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.test_strategy_name = f"TEST_Strategy_{int(time.time())}"
        self.shared_strategy_id = None
    
    def test_share_strategy(self):
        """Test POST /api/social/share - Share a strategy"""
        payload = {
            "name": self.test_strategy_name,
            "description": "Test strategy for iteration 11",
            "config": {
                "min_confidence": 60,
                "atr_sl_mult": 1.5,
                "atr_tp1_mult": 2.0,
                "atr_tp2_mult": 3.5
            },
            "performance": {
                "total_pnl": 5000,
                "total_trades": 50,
                "win_rate": 65.0,
                "score": 4500
            }
        }
        response = requests.post(f"{BASE_URL}/api/social/share", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "id" in data, "Response should contain strategy 'id'"
        assert "name" in data, "Response should contain 'name'"
        assert "config" in data, "Response should contain 'config'"
        assert "performance" in data, "Response should contain 'performance'"
        assert "author" in data, "Response should contain 'author'"
        assert "public" in data, "Response should contain 'public'"
        assert "followers" in data, "Response should contain 'followers'"
        assert "score" in data, "Response should contain 'score'"
        assert "created_at" in data, "Response should contain 'created_at'"
        
        # Verify values
        assert data["name"] == self.test_strategy_name
        assert data["public"] == True
        assert data["followers"] == 0
        assert data["score"] == 4500
        
        print(f"Shared strategy: {data['id']} by {data['author']}")
        return data["id"]
    
    def test_get_leaderboard(self):
        """Test GET /api/social/leaderboard - Get ranked strategies"""
        response = requests.get(f"{BASE_URL}/api/social/leaderboard")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "strategies" in data, "Response should contain 'strategies'"
        assert isinstance(data["strategies"], list)
        
        # If there are strategies, verify structure
        if len(data["strategies"]) > 0:
            strat = data["strategies"][0]
            assert "id" in strat
            assert "name" in strat
            assert "config" in strat
            assert "score" in strat
            print(f"Leaderboard has {len(data['strategies'])} strategies")
            print(f"Top strategy: {strat['name']} with score {strat['score']}")
        else:
            print("Leaderboard is empty")
    
    def test_follow_strategy(self):
        """Test POST /api/social/follow/{strategy_id} - Follow a strategy"""
        # First share a strategy to follow
        share_payload = {
            "name": f"TEST_FollowMe_{int(time.time())}",
            "description": "Strategy to follow",
            "config": {"min_confidence": 55, "atr_sl_mult": 1.5, "atr_tp1_mult": 2.0, "atr_tp2_mult": 3.5},
            "performance": {"total_pnl": 3000, "score": 2500}
        }
        share_response = requests.post(f"{BASE_URL}/api/social/share", json=share_payload)
        assert share_response.status_code == 200
        strategy_id = share_response.json()["id"]
        
        # Follow the strategy
        follow_response = requests.post(f"{BASE_URL}/api/social/follow/{strategy_id}")
        assert follow_response.status_code == 200, f"Expected 200, got {follow_response.status_code}: {follow_response.text}"
        
        data = follow_response.json()
        assert "action" in data
        assert data["action"] == "followed"
        assert "strategy_id" in data
        assert data["strategy_id"] == strategy_id
        assert "config" in data, "Follow response should include config to apply"
        
        print(f"Followed strategy: {strategy_id}")
        
        # Unfollow (toggle)
        unfollow_response = requests.post(f"{BASE_URL}/api/social/follow/{strategy_id}")
        assert unfollow_response.status_code == 200
        unfollow_data = unfollow_response.json()
        assert unfollow_data["action"] == "unfollowed"
        print(f"Unfollowed strategy: {strategy_id}")
    
    def test_follow_nonexistent_strategy(self):
        """Test following a non-existent strategy returns 404"""
        response = requests.post(f"{BASE_URL}/api/social/follow/nonexistent_strategy_id_12345")
        assert response.status_code == 404
    
    def test_get_following(self):
        """Test GET /api/social/following - Get strategies user is following"""
        response = requests.get(f"{BASE_URL}/api/social/following")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "following" in data, "Response should contain 'following'"
        assert isinstance(data["following"], list)
        print(f"User is following {len(data['following'])} strategies")
    
    def test_get_my_strategies(self):
        """Test GET /api/social/my-strategies - Get user's own strategies"""
        response = requests.get(f"{BASE_URL}/api/social/my-strategies")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "strategies" in data, "Response should contain 'strategies'"
        assert isinstance(data["strategies"], list)
        print(f"User has {len(data['strategies'])} shared strategies")


class TestExistingFeaturesRegression:
    """Regression tests for existing features"""
    
    def test_system_status(self):
        """Test GET /api/system/status"""
        response = requests.get(f"{BASE_URL}/api/system/status")
        assert response.status_code == 200
        data = response.json()
        assert "is_running" in data
        assert "current_symbol" in data
        assert "available_assets" in data
        print(f"System status: running={data['is_running']}, symbol={data['current_symbol']}")
    
    def test_auth_login(self):
        """Test POST /api/auth/login with admin credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@wti-trading.com",
            "password": "Admin@2026!"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "email" in data
        assert data["email"] == "admin@wti-trading.com"
        print("Admin login successful")
    
    def test_replay_simulate(self):
        """Test POST /api/replay/simulate still works"""
        response = requests.post(f"{BASE_URL}/api/replay/simulate", json={
            "event_id": "hormuz_2024",
            "config": {"min_confidence": 55, "atr_sl_mult": 1.5, "atr_tp1_mult": 2.0, "atr_tp2_mult": 3.5}
        })
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "trades" in data
        print(f"Replay simulate: {data['summary']['total_trades']} trades")
    
    def test_replay_compare(self):
        """Test POST /api/replay/compare still works"""
        response = requests.post(f"{BASE_URL}/api/replay/compare", json={
            "config": {"min_confidence": 55}
        })
        assert response.status_code == 200
        data = response.json()
        assert "events_count" in data
        assert "per_event" in data
        assert "aggregate" in data
        print(f"Replay compare: {data['events_count']} events compared")
    
    def test_bot_status(self):
        """Test GET /api/bot/status"""
        response = requests.get(f"{BASE_URL}/api/bot/status")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "min_confidence" in data
        print(f"Bot status: enabled={data['enabled']}")
    
    def test_fragility(self):
        """Test GET /api/fragility"""
        response = requests.get(f"{BASE_URL}/api/fragility")
        assert response.status_code == 200
        data = response.json()
        assert "score" in data
        assert "level" in data
        print(f"Fragility: score={data['score']}, level={data['level']}")
    
    def test_options_chain(self):
        """Test GET /api/options/chain/CL"""
        response = requests.get(f"{BASE_URL}/api/options/chain/CL")
        assert response.status_code == 200
        data = response.json()
        assert "symbol" in data
        assert "options" in data
        print(f"Options chain: {len(data['options'])} options")
    
    def test_alerts_list(self):
        """Test GET /api/alerts"""
        response = requests.get(f"{BASE_URL}/api/alerts")
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        print(f"Alerts: {len(data['alerts'])} alerts")
    
    def test_trades_export_csv(self):
        """Test GET /api/trades/export/csv"""
        response = requests.get(f"{BASE_URL}/api/trades/export/csv")
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        print("CSV export working")


class TestIntegrationFlow:
    """Integration tests for complete flows"""
    
    def test_optimizer_to_share_flow(self):
        """Test complete flow: Optimize -> Share best config"""
        # Step 1: Run optimizer
        optimize_response = requests.post(f"{BASE_URL}/api/replay/optimize", json={
            "confidence_range": [50, 60],
            "sl_range": [1.5],
            "tp1_range": [2.0],
            "tp2_range": [3.5]
        })
        assert optimize_response.status_code == 200
        best_config = optimize_response.json()["best"]
        
        # Step 2: Share the best config
        share_response = requests.post(f"{BASE_URL}/api/social/share", json={
            "name": f"TEST_Optimized_{int(time.time())}",
            "description": f"Auto-optimized config with score {best_config['score']}",
            "config": best_config["config"],
            "performance": {
                "total_pnl": best_config["total_pnl"],
                "total_trades": best_config["total_trades"],
                "win_rate": best_config["win_rate"],
                "score": best_config["score"]
            }
        })
        assert share_response.status_code == 200
        strategy_id = share_response.json()["id"]
        
        # Step 3: Verify it appears in leaderboard
        leaderboard_response = requests.get(f"{BASE_URL}/api/social/leaderboard")
        assert leaderboard_response.status_code == 200
        strategies = leaderboard_response.json()["strategies"]
        strategy_ids = [s["id"] for s in strategies]
        assert strategy_id in strategy_ids, "Shared strategy should appear in leaderboard"
        
        print(f"Complete flow: Optimized -> Shared {strategy_id} -> Verified in leaderboard")
    
    def test_follow_and_apply_config(self):
        """Test following a strategy and getting config to apply"""
        # Share a strategy
        share_response = requests.post(f"{BASE_URL}/api/social/share", json={
            "name": f"TEST_ApplyConfig_{int(time.time())}",
            "config": {"min_confidence": 70, "atr_sl_mult": 2.0, "atr_tp1_mult": 2.5, "atr_tp2_mult": 4.0},
            "performance": {"score": 5000}
        })
        assert share_response.status_code == 200
        strategy_id = share_response.json()["id"]
        
        # Follow and get config
        follow_response = requests.post(f"{BASE_URL}/api/social/follow/{strategy_id}")
        assert follow_response.status_code == 200
        data = follow_response.json()
        
        assert data["action"] == "followed"
        assert "config" in data
        assert data["config"]["min_confidence"] == 70
        assert data["config"]["atr_sl_mult"] == 2.0
        
        print(f"Followed strategy and received config: {data['config']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
