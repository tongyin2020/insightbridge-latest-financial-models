"""
Check IBKR contractDetails -> conId locked resolution for the five-model runner.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
CONNECTOR_DIR = BASE / "02_StockIndex_IBKR_ES_NQ"
if str(CONNECTOR_DIR) not in sys.path:
    sys.path.insert(0, str(CONNECTOR_DIR))

from ibkr_connector import IBKRConnector


async def main() -> int:
    connector = IBKRConnector()
    ok = await connector.connect()
    if not ok:
        print("IBKR contract resolution check failed: cannot connect to TWS paper.")
        return 1

    try:
        print("IBKR Contract Resolution Check")
        print("=" * 60)
        print(f"account: {connector.account}")
        print("-" * 60)
        for symbol, info in connector.contract_resolution.items():
            print(f"[{symbol}]")
            print(json.dumps(info, ensure_ascii=False, indent=2))
            print("-" * 60)
        return 0
    finally:
        await connector.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
