"""
Iteration 10 Backend Tests
Tests for new features:
1. Multi-Event Comparison Simulation (POST /api/replay/compare)
2. Trade Log CSV Export (GET /api/trades/export/csv)
3. Price Alerts CRUD (POST/GET/DELETE /api/alerts)
4. PWA manifest.json verification
5. Existing features regression tests
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@wti-trading.com"
ADMIN_PASSWORD = "Admin@2026!"


class TestSystemHealth:
    """Basic system health checks"""
    
    def test_root_endpoint(self):
        """Test root API endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        print(f"SUCCESS: Root endpoint returns version {data.get('version')}")
    
    def test_system_status(self):
        """Test system status endpoint"""
        response = requests.get(f"{BASE_URL}/api/system/status")
        assert response.status_code == 200
        data = response.json()
        assert "current_symbol" in data
        assert "available_assets" in data
        assert "CL" in data["available_assets"]
        print(f"SUCCESS: System status - symbol: {data['current_symbol']}, assets: {data['available_assets']}")


class TestAuthentication:
    """Authentication tests"""
    
    def test_login_success(self):
        """Test admin login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert data["email"] == ADMIN_EMAIL
        print(f"SUCCESS: Admin login works - {data['email']}")
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "wrong@example.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print("SUCCESS: Invalid credentials return 401")


class TestMultiEventComparison:
    """Tests for POST /api/replay/compare - Multi-Event Comparison Simulation"""
    
    def test_compare_all_events_default_config(self):
        """Test comparison across all events with default config"""
        response = requests.post(f"{BASE_URL}/api/replay/compare", json={
            "config": {}
        })
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "events_count" in data
        assert "per_event" in data
        assert "aggregate" in data
        assert "config" in data
        
        # Verify events_count (should be 8 historical events)
        assert data["events_count"] >= 1
        print(f"SUCCESS: Comparison ran across {data['events_count']} events")
        
        # Verify per_event structure
        assert isinstance(data["per_event"], list)
        if len(data["per_event"]) > 0:
            event = data["per_event"][0]
            assert "event_id" in event
            assert "event_name" in event
            assert "date" in event
            assert "total_trades" in event
            assert "win_rate" in event
            assert "total_pnl" in event
            assert "return_pct" in event
            assert "max_drawdown_pct" in event
            print(f"SUCCESS: Per-event data structure verified - first event: {event['event_name']}")
        
        # Verify aggregate structure
        agg = data["aggregate"]
        assert "total_pnl" in agg
        assert "total_trades" in agg
        assert "total_wins" in agg
        assert "overall_win_rate" in agg
        assert "avg_return_pct" in agg
        assert "worst_drawdown_pct" in agg
        print(f"SUCCESS: Aggregate data - Total PnL: ${agg['total_pnl']}, Win Rate: {agg['overall_win_rate']}%")
    
    def test_compare_with_custom_config(self):
        """Test comparison with custom strategy config"""
        custom_config = {
            "min_confidence": 60,
            "atr_sl_mult": 2.0,
            "atr_tp1_mult": 2.5,
            "atr_tp2_mult": 4.0
        }
        response = requests.post(f"{BASE_URL}/api/replay/compare", json={
            "config": custom_config
        })
        assert response.status_code == 200
        data = response.json()
        
        # Verify config is returned
        assert "config" in data
        print(f"SUCCESS: Custom config comparison works - config: {data['config']}")
    
    def test_compare_specific_events(self):
        """Test comparison with specific event IDs"""
        response = requests.post(f"{BASE_URL}/api/replay/compare", json={
            "event_ids": ["covid_crash_2020", "hormuz_2024"],
            "config": {}
        })
        assert response.status_code == 200
        data = response.json()
        
        # Should only have 2 events
        assert data["events_count"] <= 2
        print(f"SUCCESS: Specific events comparison - {data['events_count']} events")


class TestTradeCSVExport:
    """Tests for GET /api/trades/export/csv - Trade Log CSV Export"""
    
    def test_csv_export_returns_csv(self):
        """Test CSV export endpoint returns CSV file"""
        response = requests.get(f"{BASE_URL}/api/trades/export/csv")
        assert response.status_code == 200
        
        # Verify content type
        content_type = response.headers.get("content-type", "")
        assert "text/csv" in content_type
        print(f"SUCCESS: CSV export returns content-type: {content_type}")
        
        # Verify content disposition header
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp
        assert "filename=" in content_disp
        assert ".csv" in content_disp
        print(f"SUCCESS: CSV export has correct headers: {content_disp}")
    
    def test_csv_export_has_headers(self):
        """Test CSV export contains proper headers"""
        response = requests.get(f"{BASE_URL}/api/trades/export/csv")
        assert response.status_code == 200
        
        content = response.text
        lines = content.strip().split("\n")
        
        # First line should be headers
        assert len(lines) >= 1
        headers = lines[0].lower()
        
        # Check for expected columns
        expected_columns = ["date", "symbol", "direction", "entry", "exit", "pnl"]
        found_columns = [col for col in expected_columns if col in headers]
        print(f"SUCCESS: CSV has headers - found columns: {found_columns}")
        assert len(found_columns) >= 3  # At least some expected columns


class TestPriceAlerts:
    """Tests for Price Alerts CRUD - POST/GET/DELETE /api/alerts"""
    
    def test_get_alerts_empty(self):
        """Test getting alerts (may be empty initially)"""
        response = requests.get(f"{BASE_URL}/api/alerts")
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert isinstance(data["alerts"], list)
        print(f"SUCCESS: GET /api/alerts returns {len(data['alerts'])} alerts")
    
    def test_create_alert_above(self):
        """Test creating a price alert with 'above' condition"""
        alert_data = {
            "symbol": "CL",
            "target_price": 85.00,
            "condition": "above",
            "note": "Test alert - price above $85"
        }
        response = requests.post(f"{BASE_URL}/api/alerts", json=alert_data)
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "id" in data
        assert data["symbol"] == "CL"
        assert data["target_price"] == 85.00
        assert data["condition"] == "above"
        assert data["active"] == True
        assert data["triggered"] == False
        print(f"SUCCESS: Created alert - ID: {data['id']}, target: ${data['target_price']}")
        
        return data["id"]
    
    def test_create_alert_below(self):
        """Test creating a price alert with 'below' condition"""
        alert_data = {
            "symbol": "BZ",
            "target_price": 70.00,
            "condition": "below",
            "note": "Test alert - Brent below $70"
        }
        response = requests.post(f"{BASE_URL}/api/alerts", json=alert_data)
        assert response.status_code == 200
        data = response.json()
        
        assert data["symbol"] == "BZ"
        assert data["condition"] == "below"
        print(f"SUCCESS: Created 'below' alert for BZ at ${data['target_price']}")
        
        return data["id"]
    
    def test_create_alert_invalid_symbol(self):
        """Test creating alert with invalid symbol"""
        alert_data = {
            "symbol": "INVALID",
            "target_price": 100.00,
            "condition": "above"
        }
        response = requests.post(f"{BASE_URL}/api/alerts", json=alert_data)
        assert response.status_code == 400
        print("SUCCESS: Invalid symbol returns 400")
    
    def test_create_alert_missing_price(self):
        """Test creating alert without target_price"""
        alert_data = {
            "symbol": "CL",
            "condition": "above"
        }
        response = requests.post(f"{BASE_URL}/api/alerts", json=alert_data)
        assert response.status_code == 400
        print("SUCCESS: Missing target_price returns 400")
    
    def test_create_alert_invalid_condition(self):
        """Test creating alert with invalid condition"""
        alert_data = {
            "symbol": "CL",
            "target_price": 80.00,
            "condition": "invalid"
        }
        response = requests.post(f"{BASE_URL}/api/alerts", json=alert_data)
        assert response.status_code == 400
        print("SUCCESS: Invalid condition returns 400")
    
    def test_delete_alert(self):
        """Test deleting a price alert"""
        # First create an alert
        alert_data = {
            "symbol": "NG",
            "target_price": 4.00,
            "condition": "above",
            "note": "Test alert to delete"
        }
        create_response = requests.post(f"{BASE_URL}/api/alerts", json=alert_data)
        assert create_response.status_code == 200
        alert_id = create_response.json()["id"]
        print(f"Created alert to delete: {alert_id}")
        
        # Delete the alert
        delete_response = requests.delete(f"{BASE_URL}/api/alerts/{alert_id}")
        assert delete_response.status_code == 200
        data = delete_response.json()
        assert "message" in data
        print(f"SUCCESS: Deleted alert {alert_id}")
    
    def test_delete_nonexistent_alert(self):
        """Test deleting a non-existent alert"""
        response = requests.delete(f"{BASE_URL}/api/alerts/nonexistent_alert_id_12345")
        assert response.status_code == 404
        print("SUCCESS: Deleting non-existent alert returns 404")
    
    def test_alerts_list_after_create(self):
        """Test that created alerts appear in list"""
        # Create a unique alert
        import time
        unique_note = f"Unique test alert {time.time()}"
        alert_data = {
            "symbol": "CL",
            "target_price": 90.00,
            "condition": "above",
            "note": unique_note
        }
        create_response = requests.post(f"{BASE_URL}/api/alerts", json=alert_data)
        assert create_response.status_code == 200
        created_id = create_response.json()["id"]
        
        # Get alerts list
        list_response = requests.get(f"{BASE_URL}/api/alerts")
        assert list_response.status_code == 200
        alerts = list_response.json()["alerts"]
        
        # Find our alert
        found = any(a["id"] == created_id for a in alerts)
        assert found, f"Created alert {created_id} not found in list"
        print(f"SUCCESS: Created alert {created_id} found in alerts list")


class TestExistingFeatures:
    """Regression tests for existing features"""
    
    def test_replay_events_list(self):
        """Test replay events list still works"""
        response = requests.get(f"{BASE_URL}/api/replay/events")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert len(data["events"]) >= 1
        print(f"SUCCESS: Replay events list - {len(data['events'])} events")
    
    def test_replay_single_event(self):
        """Test single event replay still works"""
        response = requests.get(f"{BASE_URL}/api/replay/hormuz_2024")
        assert response.status_code == 200
        data = response.json()
        assert "event" in data
        assert "bars" in data
        assert "analytics" in data
        print(f"SUCCESS: Single event replay works - {data['event']['name']}")
    
    def test_replay_simulate(self):
        """Test POST /api/replay/simulate still works"""
        response = requests.post(f"{BASE_URL}/api/replay/simulate", json={
            "event_id": "covid_crash_2020",
            "config": {"min_confidence": 55}
        })
        assert response.status_code == 200
        data = response.json()
        assert "trades" in data
        assert "summary" in data
        assert "equity_curve" in data
        print(f"SUCCESS: Replay simulate works - {data['summary']['total_trades']} trades")
    
    def test_bot_status(self):
        """Test bot status endpoint"""
        response = requests.get(f"{BASE_URL}/api/bot/status")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "min_confidence" in data
        print(f"SUCCESS: Bot status - enabled: {data['enabled']}")
    
    def test_fragility(self):
        """Test fragility endpoint"""
        response = requests.get(f"{BASE_URL}/api/fragility")
        assert response.status_code == 200
        data = response.json()
        assert "score" in data
        assert "level" in data
        print(f"SUCCESS: Fragility - score: {data['score']}, level: {data['level']}")
    
    def test_options_chain(self):
        """Test options chain endpoint"""
        response = requests.get(f"{BASE_URL}/api/options/chain/CL")
        assert response.status_code == 200
        data = response.json()
        assert "symbol" in data
        assert "options" in data  # API returns 'options' not 'chain'
        print(f"SUCCESS: Options chain for CL - {len(data.get('options', []))} options")
    
    def test_notifications(self):
        """Test notifications endpoint"""
        response = requests.get(f"{BASE_URL}/api/notifications")
        assert response.status_code == 200
        data = response.json()
        assert "notifications" in data
        assert "unread_count" in data
        print(f"SUCCESS: Notifications - {data['unread_count']} unread")
    
    def test_positions(self):
        """Test positions endpoint"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"SUCCESS: Positions - {len(data)} open positions")
    
    def test_trades(self):
        """Test trades endpoint"""
        response = requests.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"SUCCESS: Trades - {len(data)} trades")
    
    def test_assets(self):
        """Test assets endpoint"""
        response = requests.get(f"{BASE_URL}/api/assets")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        symbols = [a["symbol"] for a in data]
        assert "CL" in symbols
        assert "BZ" in symbols
        assert "NG" in symbols
        print(f"SUCCESS: Assets - {symbols}")


class TestPWAManifest:
    """Tests for PWA manifest.json"""
    
    def test_manifest_exists(self):
        """Test manifest.json is accessible"""
        response = requests.get(f"{BASE_URL}/manifest.json")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required PWA fields
        assert "name" in data
        assert "short_name" in data
        assert "start_url" in data
        assert "display" in data
        assert "theme_color" in data
        assert "background_color" in data
        
        print(f"SUCCESS: PWA manifest - name: {data['name']}, short_name: {data['short_name']}")
        print(f"  display: {data['display']}, theme_color: {data['theme_color']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
