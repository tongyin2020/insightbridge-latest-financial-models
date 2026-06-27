"""
Iteration 13 Tests - Strategy Template Market Feature
Tests the new /api/social/templates and /api/social/templates/{id}/import endpoints
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestStrategyTemplatesAPI:
    """Tests for the new Strategy Template Market feature"""
    
    def test_get_templates_returns_list(self):
        """GET /api/social/templates returns list of strategy templates"""
        response = requests.get(f"{BASE_URL}/api/social/templates")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "templates" in data, "Response should contain 'templates' key"
        assert isinstance(data["templates"], list), "Templates should be a list"
        print(f"✓ GET /api/social/templates returned {len(data['templates'])} templates")
    
    def test_templates_have_required_fields(self):
        """Templates should have all required fields: id, name, author, config, total_pnl, win_rate, score, imports"""
        response = requests.get(f"{BASE_URL}/api/social/templates")
        assert response.status_code == 200
        
        data = response.json()
        templates = data["templates"]
        
        if len(templates) == 0:
            pytest.skip("No templates available to test field structure")
        
        required_fields = ["id", "name", "author", "config", "total_pnl", "win_rate", "score", "imports"]
        template = templates[0]
        
        for field in required_fields:
            assert field in template, f"Template missing required field: {field}"
        
        # Verify config structure
        config = template.get("config", {})
        assert "min_confidence" in config, "Config should have min_confidence"
        
        print(f"✓ Template has all required fields: {required_fields}")
        print(f"  Sample template: {template['name']} by {template['author']}, score={template['score']}")
    
    def test_templates_sorted_by_score(self):
        """Templates should be sorted by score in descending order"""
        response = requests.get(f"{BASE_URL}/api/social/templates")
        assert response.status_code == 200
        
        templates = response.json()["templates"]
        
        if len(templates) < 2:
            pytest.skip("Need at least 2 templates to verify sorting")
        
        scores = [t.get("score", 0) for t in templates]
        assert scores == sorted(scores, reverse=True), "Templates should be sorted by score descending"
        print(f"✓ Templates sorted by score: {scores[:5]}...")
    
    def test_import_template_success(self):
        """POST /api/social/templates/{id}/import increments imports and returns config"""
        # First get a template to import
        response = requests.get(f"{BASE_URL}/api/social/templates")
        assert response.status_code == 200
        
        templates = response.json()["templates"]
        if len(templates) == 0:
            pytest.skip("No templates available to test import")
        
        template = templates[0]
        strategy_id = template["id"]
        initial_imports = template.get("imports", 0)
        
        # Import the template
        import_response = requests.post(f"{BASE_URL}/api/social/templates/{strategy_id}/import")
        assert import_response.status_code == 200, f"Expected 200, got {import_response.status_code}"
        
        import_data = import_response.json()
        assert "strategy_id" in import_data, "Response should contain strategy_id"
        assert "config" in import_data, "Response should contain config"
        assert "name" in import_data, "Response should contain name"
        assert import_data["strategy_id"] == strategy_id, "Returned strategy_id should match"
        
        # Verify imports counter was incremented
        assert import_data.get("imports", 0) == initial_imports + 1, "Imports counter should be incremented"
        
        print(f"✓ POST /api/social/templates/{strategy_id}/import succeeded")
        print(f"  Config returned: {import_data['config']}")
        print(f"  Imports: {initial_imports} -> {import_data['imports']}")
    
    def test_import_template_404_nonexistent(self):
        """POST /api/social/templates/nonexistent/import returns 404"""
        response = requests.post(f"{BASE_URL}/api/social/templates/nonexistent_strategy_id_12345/import")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data, "404 response should contain detail message"
        print(f"✓ POST /api/social/templates/nonexistent/import returns 404: {data['detail']}")


class TestExistingSocialEndpoints:
    """Verify existing social endpoints still work after template feature addition"""
    
    def test_leaderboard_still_works(self):
        """GET /api/social/leaderboard returns strategies"""
        response = requests.get(f"{BASE_URL}/api/social/leaderboard")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "strategies" in data, "Response should contain 'strategies' key"
        print(f"✓ GET /api/social/leaderboard returned {len(data['strategies'])} strategies")
    
    def test_pvp_battle_still_works(self):
        """POST /api/social/pvp runs battle between two configs"""
        payload = {
            "name_a": "Test Strategy A",
            "name_b": "Test Strategy B",
            "config_a": {"min_confidence": 50, "atr_sl_mult": 1.5, "atr_tp1_mult": 2.0, "atr_tp2_mult": 3.5},
            "config_b": {"min_confidence": 70, "atr_sl_mult": 2.0, "atr_tp1_mult": 2.5, "atr_tp2_mult": 4.0}
        }
        response = requests.post(f"{BASE_URL}/api/social/pvp", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "overall_winner" in data, "Response should contain overall_winner"
        assert "per_event" in data, "Response should contain per_event breakdown"
        print(f"✓ POST /api/social/pvp works, winner: {data['overall_winner']}")
    
    def test_follow_strategy_still_works(self):
        """POST /api/social/follow/{id} follows/unfollows strategy"""
        # Get a strategy to follow
        response = requests.get(f"{BASE_URL}/api/social/leaderboard")
        strategies = response.json().get("strategies", [])
        
        if len(strategies) == 0:
            pytest.skip("No strategies available to test follow")
        
        strategy_id = strategies[0]["id"]
        
        # Follow the strategy
        follow_response = requests.post(f"{BASE_URL}/api/social/follow/{strategy_id}")
        assert follow_response.status_code == 200, f"Expected 200, got {follow_response.status_code}"
        
        data = follow_response.json()
        assert "action" in data, "Response should contain action"
        assert data["action"] in ["followed", "unfollowed"], f"Action should be followed or unfollowed, got {data['action']}"
        print(f"✓ POST /api/social/follow/{strategy_id} returned action: {data['action']}")
    
    def test_follow_nonexistent_returns_404(self):
        """POST /api/social/follow/nonexistent returns 404"""
        response = requests.post(f"{BASE_URL}/api/social/follow/nonexistent_strategy_xyz")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ POST /api/social/follow/nonexistent returns 404")


class TestAuthStillWorks:
    """Verify auth endpoints still work"""
    
    def test_login_with_valid_credentials(self):
        """POST /api/auth/login with valid admin credentials"""
        payload = {
            "email": "admin@wti-trading.com",
            "password": "Admin@2026!"
        }
        response = requests.post(f"{BASE_URL}/api/auth/login", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "email" in data, "Response should contain email"
        assert data["email"] == "admin@wti-trading.com"
        print(f"✓ POST /api/auth/login works for admin user")
    
    def test_login_with_invalid_credentials(self):
        """POST /api/auth/login with invalid credentials returns 401"""
        payload = {
            "email": "wrong@email.com",
            "password": "wrongpassword"
        }
        response = requests.post(f"{BASE_URL}/api/auth/login", json=payload)
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ POST /api/auth/login returns 401 for invalid credentials")


class TestTemplateImportIntegration:
    """Test the full import flow - import template and verify it can be used"""
    
    def test_import_and_verify_config_usable(self):
        """Import a template and verify the config can be used in replay simulation"""
        # Get templates
        templates_response = requests.get(f"{BASE_URL}/api/social/templates")
        assert templates_response.status_code == 200
        
        templates = templates_response.json()["templates"]
        if len(templates) == 0:
            pytest.skip("No templates available")
        
        template = templates[0]
        strategy_id = template["id"]
        
        # Import the template
        import_response = requests.post(f"{BASE_URL}/api/social/templates/{strategy_id}/import")
        assert import_response.status_code == 200
        
        imported_config = import_response.json()["config"]
        
        # Use the imported config in a replay simulation
        simulate_payload = {
            "event_id": "hormuz_2024",
            "config": imported_config
        }
        simulate_response = requests.post(f"{BASE_URL}/api/replay/simulate", json=simulate_payload)
        assert simulate_response.status_code == 200, f"Simulation failed: {simulate_response.text}"
        
        sim_data = simulate_response.json()
        assert "summary" in sim_data, "Simulation should return summary"
        print(f"✓ Imported config successfully used in replay simulation")
        print(f"  Config: {imported_config}")
        print(f"  Simulation result: PnL=${sim_data['summary'].get('total_pnl', 0)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
