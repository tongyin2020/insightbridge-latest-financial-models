#!/usr/bin/env python3
"""Test Twelve Data API connection for FX Trading System."""

import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
import os

# Load .env from the backend directory
backend_dir = Path(__file__).resolve().parent.parent / "backend"
env_path = backend_dir / ".env"
load_dotenv(env_path)

API_KEY = os.getenv("TWELVE_DATA_API_KEY")
BASE_URL = "https://api.twelvedata.com"


def check_config():
    """Check that API key is configured."""
    if not API_KEY:
        print("=" * 60)
        print("  Twelve Data API key is NOT configured")
        print("=" * 60)
        print()
        print("  To get a free API key:")
        print("  1. Go to https://twelvedata.com/")
        print("  2. Sign up for a free account")
        print("  3. Navigate to your Dashboard -> API Keys")
        print("  4. Copy your API key")
        print()
        print("  Free tier includes:")
        print("    - 800 API credits/day")
        print("    - 8 API credits/minute")
        print("    - Real-time and historical data")
        print("    - Forex, stocks, crypto, and more")
        print()
        print(f"  Add this to: {env_path}")
        print("    TWELVE_DATA_API_KEY=your_api_key_here")
        print()
        sys.exit(1)


def test_current_price():
    """Fetch AUD/USD current price."""
    print("-" * 50)
    print("Fetching AUD/USD current price...")
    print("-" * 50)
    try:
        resp = httpx.get(
            f"{BASE_URL}/price",
            params={"symbol": "AUD/USD", "apikey": API_KEY},
            timeout=15,
        )
        data = resp.json()

        if "price" in data:
            print(f"  AUD/USD: {data['price']}")
            print("  [OK] Price fetch successful.")
            return True
        elif "message" in data:
            print(f"  [FAIL] API error: {data['message']}")
            return False
        else:
            print(f"  [FAIL] Unexpected response: {data}")
            return False
    except httpx.HTTPError as e:
        print(f"  [FAIL] HTTP error: {e}")
        return False


def test_ohlc_data():
    """Fetch AUD/USD 5-minute OHLC bars."""
    print()
    print("-" * 50)
    print("Fetching AUD/USD 5-min OHLC (last 10 bars)...")
    print("-" * 50)
    try:
        resp = httpx.get(
            f"{BASE_URL}/time_series",
            params={
                "symbol": "AUD/USD",
                "interval": "5min",
                "outputsize": "10",
                "apikey": API_KEY,
            },
            timeout=15,
        )
        data = resp.json()

        if "values" in data:
            values = data["values"]
            meta = data.get("meta", {})

            if meta:
                print(f"  Symbol:   {meta.get('symbol', 'N/A')}")
                print(f"  Interval: {meta.get('interval', 'N/A')}")
                print(f"  Exchange: {meta.get('exchange', 'N/A')}")
                print()

            # Print header
            print(f"  {'Timestamp':<22} {'Open':>9} {'High':>9} {'Low':>9} {'Close':>9}")
            print(f"  {'-'*22} {'-'*9} {'-'*9} {'-'*9} {'-'*9}")

            # Print last 5 bars (most recent first)
            for bar in values[:5]:
                ts = bar.get("datetime", "N/A")
                o = bar.get("open", "N/A")
                h = bar.get("high", "N/A")
                l = bar.get("low", "N/A")
                c = bar.get("close", "N/A")
                print(f"  {ts:<22} {o:>9} {h:>9} {l:>9} {c:>9}")

            if len(values) > 5:
                print(f"  ... and {len(values) - 5} more bars")

            print()
            print(f"  [OK] Received {len(values)} OHLC bars.")
            return True

        elif "message" in data:
            print(f"  [FAIL] API error: {data['message']}")
            return False
        else:
            print(f"  [FAIL] Unexpected response: {data}")
            return False
    except httpx.HTTPError as e:
        print(f"  [FAIL] HTTP error: {e}")
        return False


def test_api_usage():
    """Check API usage if available."""
    print()
    print("-" * 50)
    print("Checking API usage...")
    print("-" * 50)
    try:
        resp = httpx.get(
            f"{BASE_URL}/api_usage",
            params={"apikey": API_KEY},
            timeout=15,
        )
        data = resp.json()

        if "current_usage" in data or "daily_usage" in data:
            daily = data.get("daily_usage", data.get("current_usage", 0))
            plan = data.get("plan_limit", data.get("plan_daily_limit", "N/A"))
            print(f"  Daily usage:  {daily}")
            print(f"  Daily limit:  {plan}")
            print("  [OK] Usage info retrieved.")
            return True
        elif "message" in data:
            # Some plans may not support this endpoint
            print(f"  [INFO] {data['message']}")
            print("  (API usage endpoint may not be available on all plans)")
            return True
        else:
            print(f"  [INFO] Response: {data}")
            return True
    except httpx.HTTPError as e:
        print(f"  [WARN] Could not fetch usage info: {e}")
        return True  # Non-critical


def main():
    print()
    print("=" * 50)
    print("  FX Trading System - Twelve Data API Test")
    print("=" * 50)
    print(f"  .env path: {env_path}")
    print()

    check_config()

    price_ok = test_current_price()
    ohlc_ok = test_ohlc_data()
    test_api_usage()

    print()
    print("=" * 50)
    if price_ok and ohlc_ok:
        print("  ALL TESTS PASSED")
    else:
        print("  SOME TESTS FAILED")
        if not price_ok:
            print("    - Price fetch failed")
        if not ohlc_ok:
            print("    - OHLC fetch failed")
    print("=" * 50)
    print()

    sys.exit(0 if (price_ok and ohlc_ok) else 1)


if __name__ == "__main__":
    main()
