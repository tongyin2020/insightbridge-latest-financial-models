#!/usr/bin/env python3
"""
FX Trading System Backend API Test Suite
Tests all endpoints for AUD/USD and NZD/USD forex trading system
"""

import requests
import json
import time
import sys
from datetime import datetime
from typing import Dict, Any, Optional

class FXTradingSystemTester:
    def __init__(self, base_url: str = "https://aud-nzd-signals.preview.emergentagent.com"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
    def log_test(self, name: str, success: bool, details: str = "", response_data: Any = None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name} - {details}")
        
        self.test_results.append({
            "test": name,
            "success": success,
            "details": details,
            "response_data": response_data,
            "timestamp": datetime.now().isoformat()
        })
    
    def test_health_endpoint(self) -> bool:
        """Test system health and configuration"""
        try:
            response = self.session.get(f"{self.base_url}/api/health", timeout=10)
            
            if response.status_code != 200:
                self.log_test("Health Check", False, f"Status {response.status_code}")
                return False
            
            data = response.json()
            required_fields = ["status", "data_source", "pairs", "event_state"]
            
            for field in required_fields:
                if field not in data:
                    self.log_test("Health Check", False, f"Missing field: {field}")
                    return False
            
            # Verify pairs
            if "AUD/USD" not in data["pairs"] or "NZD/USD" not in data["pairs"]:
                self.log_test("Health Check", False, "Missing required currency pairs")
                return False
            
            self.log_test("Health Check", True, f"Status: {data['status']}, Source: {data['data_source']}")
            return True
            
        except Exception as e:
            self.log_test("Health Check", False, f"Exception: {str(e)}")
            return False
    
    def test_price_endpoints(self) -> bool:
        """Test real-time price data for both pairs"""
        pairs = ["AUD/USD", "NZD/USD"]
        all_passed = True
        
        for pair in pairs:
            try:
                # Test current price
                pair_url = pair.replace("/", "_")
                response = self.session.get(f"{self.base_url}/api/prices/{pair_url}", timeout=10)
                
                if response.status_code != 200:
                    self.log_test(f"Price Data - {pair}", False, f"Status {response.status_code}")
                    all_passed = False
                    continue
                
                data = response.json()
                price_data = data.get("price", {})
                
                # Verify price fields
                required_price_fields = ["bid", "ask", "mid", "spread_pips", "timestamp"]
                for field in required_price_fields:
                    if field not in price_data:
                        self.log_test(f"Price Data - {pair}", False, f"Missing price field: {field}")
                        all_passed = False
                        continue
                
                # Verify indicators
                indicators = data.get("indicators", {})
                required_indicators = ["sma20", "sma50", "adx", "rsi", "atr", "regime"]
                for indicator in required_indicators:
                    if indicator not in indicators:
                        self.log_test(f"Price Data - {pair}", False, f"Missing indicator: {indicator}")
                        all_passed = False
                        continue
                
                self.log_test(f"Price Data - {pair}", True, 
                            f"Mid: {price_data['mid']}, Regime: {indicators.get('regime', 'N/A')}")
                
                # Test price history
                response = self.session.get(f"{self.base_url}/api/prices/{pair_url}/history?limit=50", timeout=10)
                if response.status_code == 200:
                    history_data = response.json()
                    if "prices" in history_data and len(history_data["prices"]) > 0:
                        self.log_test(f"Price History - {pair}", True, 
                                    f"Retrieved {len(history_data['prices'])} historical bars")
                    else:
                        self.log_test(f"Price History - {pair}", False, "No historical data")
                        all_passed = False
                else:
                    self.log_test(f"Price History - {pair}", False, f"Status {response.status_code}")
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Price Data - {pair}", False, f"Exception: {str(e)}")
                all_passed = False
        
        return all_passed
    
    def test_technical_indicators(self) -> bool:
        """Test technical indicators calculation"""
        try:
            # Get price data with indicators
            response = self.session.get(f"{self.base_url}/api/prices/AUD_USD", timeout=10)
            
            if response.status_code != 200:
                self.log_test("Technical Indicators", False, f"Status {response.status_code}")
                return False
            
            data = response.json()
            indicators = data.get("indicators", {})
            
            # Check if indicators are calculated (not None)
            indicator_tests = {
                "SMA20": indicators.get("sma20"),
                "SMA50": indicators.get("sma50"), 
                "ADX": indicators.get("adx"),
                "RSI": indicators.get("rsi"),
                "ATR": indicators.get("atr"),
                "Bollinger Bands": indicators.get("bb_upper") and indicators.get("bb_lower")
            }
            
            all_calculated = True
            for name, value in indicator_tests.items():
                if value is None:
                    self.log_test(f"Technical Indicators - {name}", False, "Not calculated")
                    all_calculated = False
                else:
                    self.log_test(f"Technical Indicators - {name}", True, f"Value: {value}")
            
            return all_calculated
            
        except Exception as e:
            self.log_test("Technical Indicators", False, f"Exception: {str(e)}")
            return False
    
    def test_event_engine(self) -> bool:
        """Test 30-second event cooldown mechanism"""
        try:
            # Test event state
            response = self.session.get(f"{self.base_url}/api/events/state", timeout=10)
            if response.status_code != 200:
                self.log_test("Event Engine - State", False, f"Status {response.status_code}")
                return False
            
            initial_state = response.json()
            self.log_test("Event Engine - State", True, f"Current state: {initial_state.get('state', 'N/A')}")
            
            # Test manual event trigger
            trigger_data = {"level": "A", "title": "Test Event Trigger"}
            response = self.session.post(f"{self.base_url}/api/event/trigger", 
                                       json=trigger_data, timeout=10)
            
            if response.status_code != 200:
                self.log_test("Event Engine - Trigger", False, f"Status {response.status_code}")
                return False
            
            trigger_result = response.json()
            if trigger_result.get("state") == "COOLDOWN":
                self.log_test("Event Engine - Trigger", True, 
                            f"Cooldown started, remaining: {trigger_result.get('remaining_seconds', 0)}s")
            else:
                self.log_test("Event Engine - Trigger", False, f"Unexpected state: {trigger_result.get('state')}")
                return False
            
            # Test event reset
            response = self.session.post(f"{self.base_url}/api/event/reset", timeout=10)
            if response.status_code == 200:
                reset_result = response.json()
                self.log_test("Event Engine - Reset", True, f"Reset to state: {reset_result.get('state', 'N/A')}")
            else:
                self.log_test("Event Engine - Reset", False, f"Status {response.status_code}")
                return False
            
            return True
            
        except Exception as e:
            self.log_test("Event Engine", False, f"Exception: {str(e)}")
            return False
    
    def test_ai_analysis(self) -> bool:
        """Test AI analysis with GPT-5.2"""
        try:
            # Test AI analysis for AUD/USD
            analysis_data = {"pair": "AUD/USD"}
            response = self.session.post(f"{self.base_url}/api/ai/analyze", 
                                       json=analysis_data, timeout=30)
            
            if response.status_code != 200:
                self.log_test("AI Analysis", False, f"Status {response.status_code}")
                return False
            
            result = response.json()
            
            if result.get("status") == "error":
                self.log_test("AI Analysis", False, f"AI Error: {result.get('analysis', 'Unknown error')}")
                return False
            
            if result.get("status") == "success" and result.get("analysis"):
                self.log_test("AI Analysis", True, f"Analysis generated for {result.get('pair')}")
                
                # Test AI history
                response = self.session.get(f"{self.base_url}/api/ai/history?limit=5", timeout=10)
                if response.status_code == 200:
                    history = response.json()
                    self.log_test("AI History", True, f"Retrieved {len(history.get('analyses', []))} analyses")
                else:
                    self.log_test("AI History", False, f"Status {response.status_code}")
                
                return True
            else:
                self.log_test("AI Analysis", False, "No analysis content returned")
                return False
            
        except Exception as e:
            self.log_test("AI Analysis", False, f"Exception: {str(e)}")
            return False
    
    def test_trading_signals(self) -> bool:
        """Test trading signal generation"""
        try:
            response = self.session.get(f"{self.base_url}/api/signals/current", timeout=10)
            
            if response.status_code != 200:
                self.log_test("Trading Signals", False, f"Status {response.status_code}")
                return False
            
            data = response.json()
            signals = data.get("signals", {})
            
            # Check signals for both pairs
            pairs = ["AUD/USD", "NZD/USD"]
            all_signals_present = True
            
            for pair in pairs:
                if pair in signals:
                    signal = signals[pair]
                    direction = signal.get("direction", "N/A")
                    confidence = signal.get("confidence", 0)
                    self.log_test(f"Trading Signals - {pair}", True, 
                                f"Direction: {direction}, Confidence: {confidence}%")
                else:
                    self.log_test(f"Trading Signals - {pair}", False, "No signal data")
                    all_signals_present = False
            
            return all_signals_present
            
        except Exception as e:
            self.log_test("Trading Signals", False, f"Exception: {str(e)}")
            return False
    
    def test_settings_and_kill_switch(self) -> bool:
        """Test settings management and Kill Switch"""
        try:
            # Get current settings
            response = self.session.get(f"{self.base_url}/api/settings", timeout=10)
            if response.status_code != 200:
                self.log_test("Settings - Get", False, f"Status {response.status_code}")
                return False
            
            settings = response.json()
            self.log_test("Settings - Get", True, f"Retrieved {len(settings)} settings")
            
            # Test Kill Switch toggle
            current_kill_switch = settings.get("kill_switch", "false")
            new_value = "true" if current_kill_switch == "false" else "false"
            
            response = self.session.put(f"{self.base_url}/api/settings/kill_switch",
                                      json={"value": new_value}, timeout=10)
            
            if response.status_code == 200:
                self.log_test("Kill Switch - Update", True, f"Set to: {new_value}")
                
                # Reset to original value
                self.session.put(f"{self.base_url}/api/settings/kill_switch",
                               json={"value": current_kill_switch}, timeout=10)
            else:
                self.log_test("Kill Switch - Update", False, f"Status {response.status_code}")
                return False
            
            # Test direction permissions
            response = self.session.put(f"{self.base_url}/api/settings/aud_usd_direction",
                                      json={"value": "BOTH"}, timeout=10)
            
            if response.status_code == 200:
                self.log_test("Direction Permissions", True, "AUD/USD set to BOTH")
            else:
                self.log_test("Direction Permissions", False, f"Status {response.status_code}")
                return False
            
            return True
            
        except Exception as e:
            self.log_test("Settings", False, f"Exception: {str(e)}")
            return False
    
    def test_broker_status(self) -> bool:
        """Test broker connection status"""
        try:
            response = self.session.get(f"{self.base_url}/api/broker/status", timeout=10)
            
            if response.status_code != 200:
                self.log_test("Broker Status", False, f"Status {response.status_code}")
                return False
            
            data = response.json()
            
            # Check broker configurations
            if "dukascopy" in data and "interactive_brokers" in data:
                self.log_test("Broker Status", True, "Broker configurations retrieved")
            else:
                self.log_test("Broker Status", False, "Missing broker data")
                return False
            
            # Test data sources
            response = self.session.get(f"{self.base_url}/api/broker/datasources", timeout=10)
            if response.status_code == 200:
                sources = response.json()
                self.log_test("Data Sources", True, f"Retrieved {len(sources)} data sources")
            else:
                self.log_test("Data Sources", False, f"Status {response.status_code}")
                return False
            
            return True
            
        except Exception as e:
            self.log_test("Broker Status", False, f"Exception: {str(e)}")
            return False
    
    def test_economic_calendar(self) -> bool:
        """Test economic calendar events"""
        try:
            response = self.session.get(f"{self.base_url}/api/events", timeout=10)
            
            if response.status_code != 200:
                self.log_test("Economic Calendar", False, f"Status {response.status_code}")
                return False
            
            data = response.json()
            events = data.get("events", [])
            
            if len(events) > 0:
                # Check event structure
                event = events[0]
                required_fields = ["title", "country", "impact", "datetime", "pair_affected"]
                
                for field in required_fields:
                    if field not in event:
                        self.log_test("Economic Calendar", False, f"Missing event field: {field}")
                        return False
                
                self.log_test("Economic Calendar", True, f"Retrieved {len(events)} events")
                return True
            else:
                self.log_test("Economic Calendar", False, "No events found")
                return False
            
        except Exception as e:
            self.log_test("Economic Calendar", False, f"Exception: {str(e)}")
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run comprehensive test suite"""
        print("🚀 Starting FX Trading System Backend Tests...")
        print(f"📡 Testing endpoint: {self.base_url}")
        print("=" * 60)
        
        # Core system tests
        self.test_health_endpoint()
        self.test_price_endpoints()
        self.test_technical_indicators()
        
        # Feature tests
        self.test_event_engine()
        self.test_trading_signals()
        self.test_settings_and_kill_switch()
        
        # Integration tests
        self.test_ai_analysis()
        self.test_broker_status()
        self.test_economic_calendar()
        
        print("=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        return {
            "total_tests": self.tests_run,
            "passed_tests": self.tests_passed,
            "success_rate": round(success_rate, 1),
            "test_results": self.test_results,
            "timestamp": datetime.now().isoformat()
        }

def main():
    """Main test execution"""
    tester = FXTradingSystemTester()
    results = tester.run_all_tests()
    
    # Save results
    with open("/app/test_reports/backend_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    # Exit with appropriate code
    if results["success_rate"] >= 80:
        print("✅ Backend tests completed successfully!")
        return 0
    else:
        print("❌ Backend tests failed - multiple issues detected")
        return 1

if __name__ == "__main__":
    sys.exit(main())