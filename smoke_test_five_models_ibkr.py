#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
MOD_DIR = BASE / "02_StockIndex_IBKR_ES_NQ"
if str(MOD_DIR) not in sys.path:
    sys.path.insert(0, str(MOD_DIR))

from ibkr_connector import IBKRConnector, CONTRACTS  # type: ignore


async def main() -> int:
    connector = IBKRConnector()
    report: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": connector.ib.client.host if getattr(connector.ib, "client", None) else None,
        "symbols": {},
    }

    print("IBKR Five-Model Smoke Test")
    print("=" * 60)
    connected = await connector.connect()
    if not connected:
        print("status: ATTENTION")
        print("reason: connector could not reach TWS paper port")
        return 1

    summary = await connector.get_account_summary()
    print(f"account: {connector.account}")
    print(f"net_liq: {summary.get('NetLiquidation', 0):,.2f}")
    print(f"available_funds: {summary.get('AvailableFunds', 0):,.2f}")
    print("-" * 60)

    for symbol in CONTRACTS:
        try:
            contract = await connector.get_contract(symbol)
            report["symbols"][symbol] = {
                "ok": True,
                "contract": str(contract),
                "conId": getattr(contract, "conId", 0),
                "localSymbol": getattr(contract, "localSymbol", ""),
                "expiry": getattr(contract, "lastTradeDateOrContractMonth", ""),
            }
            print(f"[OK] {symbol}: qualified")
        except Exception as exc:
            report["symbols"][symbol] = {"ok": False, "error": str(exc)}
            print(f"[ATTENTION] {symbol}: {exc}")

    out = BASE / "reports" / "ibkr_five_model_smoke_test.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print("-" * 60)
    print(f"saved_report: {out}")
    await connector.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
