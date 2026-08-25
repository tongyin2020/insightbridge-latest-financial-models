#!/usr/bin/env python3
"""加密货币实时行情（美区可用 · Coinbase 公共接口）

用法：
  python3 crypto_market_data.py --snapshot          # 一次快照（REST，BTC/ETH/SOL 现价+买卖价）
  python3 crypto_market_data.py --stream [--seconds 15]  # 实时 WebSocket 流

说明：
- Binance.com 在美区被地理封锁，改用 Coinbase（美区最大交易所，BTC/ETH/SOL 全有）。
- REST：api.coinbase.com/v2/prices（现货价）；api.exchange.coinbase.com/products/{pair}/ticker（含 bid/ask）。
- WebSocket：wss://ws-feed.exchange.coinbase.com（公开 ticker，无需认证）。
"""
import argparse
import json
import time
import urllib.request

PAIRS = ["BTC-USD", "ETH-USD", "SOL-USD"]


def snapshot():
    print("=== Coinbase 现货快照 ===")
    for p in PAIRS:
        try:
            # 现货价
            r = urllib.request.urlopen(
                f"https://api.coinbase.com/v2/prices/{p}/spot", timeout=10)
            spot = json.load(r)["data"]["amount"]
            # 盘口价（exchange API）
            try:
                r2 = urllib.request.urlopen(
                    f"https://api.exchange.coinbase.com/products/{p}/ticker", timeout=10)
                t = json.load(r2)
                bid, ask, last = t.get("bid"), t.get("ask"), t.get("price")
                print(f"  {p:8} spot={spot:>12}  bid={bid:>12}  ask={ask:>12}  last={last}")
            except Exception:
                print(f"  {p:8} spot={spot}")
        except Exception as e:
            print(f"  {p}: ERROR {e}")


def stream(seconds):
    import websocket  # websocket-client
    ws = websocket.WebSocket()
    url = "wss://ws-feed.exchange.coinbase.com"
    print(f"连接 {url} ...")
    ws.connect(url, timeout=15)
    ws.send(json.dumps({
        "type": "subscribe",
        "product_ids": PAIRS,
        "channels": ["ticker"],
    }))
    print(f"已订阅 {PAIRS}，流式打印 {seconds}s ...")
    end = time.time() + seconds
    n = 0
    while time.time() < end:
        ws.settimeout(end - time.time())
        try:
            msg = ws.recv()
        except Exception:
            break
        d = json.loads(msg)
        if d.get("type") == "ticker":
            n += 1
            print(f"  {d.get('product_id'):8} price={d.get('price'):>12} "
                  f"bid={d.get('best_bid'):>12} ask={d.get('best_ask'):>12}")
        if n >= 30:
            break
    ws.close()
    print(f"收到 {n} 条 ticker。")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--stream", action="store_true")
    ap.add_argument("--seconds", type=int, default=15)
    a = ap.parse_args()
    if a.stream:
        stream(a.seconds)
    else:
        snapshot()
