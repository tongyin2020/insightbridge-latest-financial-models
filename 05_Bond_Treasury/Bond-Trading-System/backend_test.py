import requests
import sys
import json
from datetime import datetime

class AIBondTradingV3Tester:
    def __init__(self, base_url="https://rate-trading-auto.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.session = requests.Session()

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        # Add auth token if available
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = self.session.get(url, headers=headers, params=params)
            elif method == 'POST':
                response = self.session.post(url, json=data, headers=headers, params=params)
            elif method == 'DELETE':
                response = self.session.delete(url, headers=headers, params=params)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    if isinstance(response_data, list):
                        print(f"   Response: List with {len(response_data)} items")
                    elif isinstance(response_data, dict):
                        print(f"   Response keys: {list(response_data.keys())}")
                    return True, response_data
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                except:
                    print(f"   Error: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_login(self):
        """Test login with admin credentials"""
        print("\n🔐 Testing Authentication...")
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "api/auth/login",
            200,
            data={"email": "admin@trading.com", "password": "Admin@123456"}
        )
        
        if success:
            # Check if we got cookies (httpOnly) or token in response
            if 'access_token' in response:
                self.token = response['access_token']
            # For httpOnly cookies, the session will handle it automatically
            print("   ✅ Login successful - session established")
            return True
        return False

    def test_assets_api(self):
        """Test assets API endpoints"""
        print("\n📊 Testing Assets API...")
        
        # Test get all assets
        success, assets = self.run_test(
            "Get Available Assets",
            "GET",
            "api/assets",
            200
        )
        
        if not success:
            return False
            
        if not isinstance(assets, list) or len(assets) == 0:
            print("❌ Assets API returned empty or invalid data")
            return False
            
        print(f"   ✅ Found {len(assets)} available assets")
        
        # Verify expected assets are present
        expected_assets = ['10Y_BOND', 'WTI', 'GOLD', 'EUR_USD', 'SP500', 'BTC']
        found_symbols = [asset.get('symbol') for asset in assets]
        
        for expected in expected_assets:
            if expected in found_symbols:
                print(f"   ✅ Found expected asset: {expected}")
            else:
                print(f"   ⚠️  Missing expected asset: {expected}")
        
        return True

    def test_asset_prices_api(self):
        """Test asset prices API"""
        print("\n💰 Testing Asset Prices API...")
        
        success, prices = self.run_test(
            "Get Asset Prices",
            "GET",
            "api/assets/prices",
            200
        )
        
        if not success:
            return False
            
        if not isinstance(prices, list) or len(prices) == 0:
            print("❌ Asset prices API returned empty or invalid data")
            return False
            
        print(f"   ✅ Found prices for {len(prices)} assets")
        
        # Check price data structure
        for price in prices[:3]:  # Check first 3 prices
            required_fields = ['symbol', 'name', 'asset_type', 'price', 'change_pct']
            missing_fields = [field for field in required_fields if field not in price]
            if missing_fields:
                print(f"   ⚠️  Missing fields in price data: {missing_fields}")
            else:
                print(f"   ✅ Valid price data for {price['symbol']}: ${price['price']}")
        
        return True

    def test_paper_trading_api(self):
        """Test paper trading functionality"""
        print("\n📝 Testing Paper Trading API...")
        
        # Test get paper portfolio
        success, portfolio = self.run_test(
            "Get Paper Portfolio",
            "GET",
            "api/paper-trading/portfolio",
            200
        )
        
        if not success:
            return False
            
        print(f"   ✅ Paper portfolio loaded - Cash: ${portfolio.get('cash', 0)}")
        
        # Test paper trade execution
        success, trade_result = self.run_test(
            "Execute Paper BUY Trade",
            "POST",
            "api/paper-trading/trade",
            200,
            params={"asset": "WTI", "quantity": 10, "action": "BUY"}
        )
        
        if not success:
            print("   ❌ Paper trade execution failed")
            return False
            
        print(f"   ✅ Paper BUY trade executed successfully")
        
        # Test get paper trade history
        success, history = self.run_test(
            "Get Paper Trade History",
            "GET",
            "api/paper-trading/history",
            200,
            params={"limit": 10}
        )
        
        if success and isinstance(history, list):
            print(f"   ✅ Paper trade history loaded - {len(history)} trades")
        
        return True

    def test_strategy_marketplace_api(self):
        """Test strategy marketplace functionality"""
        print("\n🏪 Testing Strategy Marketplace API...")
        
        # Test get marketplace strategies
        success, strategies = self.run_test(
            "Get Marketplace Strategies",
            "GET",
            "api/marketplace/strategies",
            200,
            params={"sort_by": "subscribers"}
        )
        
        if not success:
            return False
            
        print(f"   ✅ Marketplace strategies loaded - {len(strategies)} strategies")
        
        # Test publish a strategy
        strategy_name = f"Test Strategy {datetime.now().strftime('%H%M%S')}"
        success, published = self.run_test(
            "Publish Strategy",
            "POST",
            "api/marketplace/strategies/publish",
            200,
            data={
                "ispread_upper": 15.0,
                "ispread_lower": 10.0,
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.10
            },
            params={
                "name": strategy_name,
                "description": "Test strategy for API testing",
                "strategy_type": "AI_HYBRID"
            }
        )
        
        if success:
            print(f"   ✅ Strategy published successfully: {strategy_name}")
            strategy_id = published.get('id')
            
            # Test get user's published strategies
            success, my_strategies = self.run_test(
                "Get My Published Strategies",
                "GET",
                "api/marketplace/my-strategies",
                200
            )
            
            if success:
                print(f"   ✅ User strategies loaded - {len(my_strategies)} strategies")
            
            return True
        else:
            print("   ❌ Strategy publishing failed")
            return False

    def test_auth_endpoints(self):
        """Test additional auth endpoints"""
        print("\n🔒 Testing Auth Endpoints...")
        
        # Test get current user
        success, user = self.run_test(
            "Get Current User",
            "GET",
            "api/auth/me",
            200
        )
        
        if success:
            print(f"   ✅ Current user: {user.get('email', 'Unknown')}")
            return True
        return False

def main():
    print("🚀 AI Bond Trading System V3 - API Testing")
    print("=" * 50)
    
    tester = AIBondTradingV3Tester()
    
    # Test sequence
    tests = [
        ("Authentication", tester.test_login),
        ("Auth Endpoints", tester.test_auth_endpoints),
        ("Assets API", tester.test_assets_api),
        ("Asset Prices API", tester.test_asset_prices_api),
        ("Paper Trading API", tester.test_paper_trading_api),
        ("Strategy Marketplace API", tester.test_strategy_marketplace_api),
    ]
    
    failed_tests = []
    
    for test_name, test_func in tests:
        try:
            if not test_func():
                failed_tests.append(test_name)
        except Exception as e:
            print(f"\n❌ {test_name} failed with exception: {e}")
            failed_tests.append(test_name)
    
    # Print results
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {tester.tests_passed}/{tester.tests_run} tests passed")
    
    if failed_tests:
        print(f"❌ Failed test categories: {', '.join(failed_tests)}")
        return 1
    else:
        print("✅ All test categories passed!")
        return 0

if __name__ == "__main__":
    sys.exit(main())