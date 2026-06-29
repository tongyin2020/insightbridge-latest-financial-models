#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
ROOT = "http://127.0.0.1:8001"
RUNTIME_PAIRS = ["AUD/USD", "NZD/USD", "EUR/USD", "USD/JPY", "GBP/USD", "AUD/JPY", "NZD/JPY"]
PROBE_INPUT = "AUD/USD,NZD/USD,EUR/USD,USD/JPY,GBP/USD,AUD/JPY,NZD/JPY"
PRIMARY_PAIRS = ["AUD/USD", "NZD/USD", "EUR/USD", "USD/JPY", "GBP/USD"]
SECONDARY_READY_PAIRS = ["AUD/JPY", "NZD/JPY"]


def fetch_json(path: str) -> dict | None:
    try:
        with urlopen(ROOT + path, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def main() -> int:
    health = fetch_json("/api/health")
    duk = fetch_json("/api/broker/dukascopy/status")

    print("InsightBridge Dukascopy Seven-FX Runtime Check")
    print("=" * 60)
    print(f"project: {BASE}")
    print(f"recommended_jforex_pairs_csv: {PROBE_INPUT}")
    print(f"primary_runtime_pairs: {', '.join(PRIMARY_PAIRS)}")
    print(f"secondary_ready_pairs: {', '.join(SECONDARY_READY_PAIRS)}")
    print(f"target_runtime_pairs: {', '.join(RUNTIME_PAIRS)}")
    print("-" * 60)

    if not health:
        print("backend_api: UNREACHABLE")
        print("Overall: ATTENTION")
        return 1

    backend_pairs = health.get("pairs", [])
    print(f"backend_api: LIVE | status={health.get('status')}")
    print(f"backend_pairs: {', '.join(backend_pairs)}")
    print(f"event_state: {health.get('event_state')}")
    print("-" * 60)

    missing = [pair for pair in RUNTIME_PAIRS if pair not in backend_pairs]
    extra = [pair for pair in backend_pairs if pair not in RUNTIME_PAIRS]
    print(f"missing_from_backend_config: {missing or 'none'}")
    print(f"extra_in_backend_config: {extra or 'none'}")
    print("-" * 60)

    if duk:
        print("[Dukascopy Adapter]")
        print(f"connected: {duk.get('connected')}")
        print(f"status: {duk.get('status')}")
        latest_ticks = duk.get("latest_ticks", {})
        if latest_ticks:
            for pair in RUNTIME_PAIRS:
                tick = latest_ticks.get(pair)
                if tick:
                    print(f"{pair}: mid={tick.get('mid')} spread_pips={tick.get('spread_pips')}")
                else:
                    print(f"{pair}: no tick yet")
        else:
            print("latest_ticks: none")
        print("-" * 60)

    overall = "READY" if not missing else "PARTIAL"
    print(f"Overall: {overall}")
    return 0 if overall == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
