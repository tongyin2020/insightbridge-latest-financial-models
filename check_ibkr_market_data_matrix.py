#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
MOD_DIR = BASE / "02_StockIndex_IBKR_ES_NQ"
if str(MOD_DIR) not in sys.path:
    sys.path.insert(0, str(MOD_DIR))

from ibkr_connector import IBKRConnector, CONTRACTS  # type: ignore

REPORTS_DIR = BASE / "reports" / "market_data_diagnostics"

ERROR_MAP = {
    10197: ("competing_session", "另一个 IBKR 会话正在占用实时行情"),
    10167: ("delayed_only", "当前只有延迟/冻结行情，没有实时订阅"),
    10090: ("subscription_limited", "市场数据订阅不足或品种权限不完整"),
    354: ("subscription_limited", "没有该合约所需的市场数据订阅"),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def price_from_ticker(ticker) -> float | None:
    for field in ("last", "bid", "ask", "close"):
        value = getattr(ticker, field, None)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return None


def infer_primary_cause(statuses: list[str], has_price: bool, symbol: str) -> tuple[str, str]:
    if "competing_session" in statuses:
        return "competing_session", "会话冲突，不是代码故障"
    if "subscription_limited" in statuses:
        return "subscription_missing", "订阅不足，尤其是该品种的实时行情权限不完整"
    if "delayed_only" in statuses:
        if symbol in {"ZN", "CL", "MES", "ES_PROXY"}:
            return "delayed_and_market_hours", "期货更像是实时订阅不足；周日/休市只会让问题更明显"
        return "delayed_only", "拿到的是延迟/冻结行情，不是完整实时 feed"
    if has_price:
        return "ok", "行情可用"
    return "unknown", "没有足够行情返回，需进一步人工核查"


async def diagnose_symbol(connector: IBKRConnector, symbol: str) -> dict[str, Any]:
    contract = await connector.get_contract(symbol)
    symbol_state: dict[str, Any] = {
        "symbol": symbol,
        "contract": {
            "secType": getattr(contract, "secType", ""),
            "exchange": getattr(contract, "exchange", ""),
            "localSymbol": getattr(contract, "localSymbol", ""),
            "conId": getattr(contract, "conId", 0),
            "expiry": getattr(contract, "lastTradeDateOrContractMonth", ""),
        },
        "realtime": {},
        "delayed": {},
        "diagnosis": {},
    }

    captured_errors: list[dict[str, Any]] = []

    def on_error(reqId, errorCode, errorString, err_contract=None):
        if err_contract is None:
            return
        local_symbol = getattr(err_contract, "localSymbol", None)
        base_symbol = getattr(err_contract, "symbol", None)
        if local_symbol == getattr(contract, "localSymbol", None) or base_symbol == getattr(contract, "symbol", None):
            captured_errors.append(
                {
                    "reqId": reqId,
                    "errorCode": errorCode,
                    "errorString": errorString,
                }
            )

    connector.ib.errorEvent += on_error
    try:
        for label, market_data_type in (("realtime", 1), ("delayed", 4)):
            start_error_index = len(captured_errors)
            connector.ib.reqMarketDataType(market_data_type)
            ticker = connector.ib.reqMktData(contract, "", False, False)
            await asyncio.sleep(3.0)
            price = price_from_ticker(ticker)
            snapshot_errors = captured_errors[start_error_index:]
            statuses = []
            details = []
            for err in snapshot_errors:
                mapped = ERROR_MAP.get(err["errorCode"])
                if mapped:
                    statuses.append(mapped[0])
                    details.append(mapped[1])
                else:
                    statuses.append(f"error_{err['errorCode']}")
                    details.append(err["errorString"])
            if price is not None and not statuses:
                statuses = ["ok"]
                details = ["拿到了价格，且没有权限/会话错误"]
            elif price is not None and "ok" not in statuses:
                statuses.append("has_price")
                details.append("虽然有错误提示，但仍返回了价格")

            symbol_state[label] = {
                "market_data_type": market_data_type,
                "price": price,
                "bid": getattr(ticker, "bid", None),
                "ask": getattr(ticker, "ask", None),
                "last": getattr(ticker, "last", None),
                "close": getattr(ticker, "close", None),
                "statuses": statuses,
                "details": details,
                "errors": snapshot_errors,
            }
            connector.ib.cancelMktData(contract)
            await asyncio.sleep(0.25)
    finally:
        try:
            connector.ib.errorEvent -= on_error
        except Exception:
            pass

    all_statuses = list(symbol_state["realtime"].get("statuses", [])) + list(symbol_state["delayed"].get("statuses", []))
    has_price = bool(symbol_state["realtime"].get("price") or symbol_state["delayed"].get("price"))
    cause_code, cause_text = infer_primary_cause(all_statuses, has_price, symbol)
    symbol_state["diagnosis"] = {
        "primary_cause_code": cause_code,
        "primary_cause": cause_text,
        "weekend_factor": symbol in {"ZN", "CL", "MES", "ES_PROXY"},
        "has_any_price": has_price,
    }
    return symbol_state


async def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    connector = IBKRConnector()
    ok = await connector.connect()
    if not ok:
        print("IBKR Market Data Matrix")
        print("=" * 60)
        print("status: ATTENTION")
        print("reason: cannot connect to IBKR paper API")
        return 1

    try:
        results = []
        for symbol in CONTRACTS:
            if symbol == "ES_PROXY":
                continue
            try:
                results.append(await diagnose_symbol(connector, symbol))
            except Exception as exc:
                results.append(
                    {
                        "symbol": symbol,
                        "diagnosis": {
                            "primary_cause_code": "error",
                            "primary_cause": str(exc),
                            "weekend_factor": symbol in {"ZN", "CL", "MES"},
                            "has_any_price": False,
                        },
                    }
                )

        payload = {
            "generated_at": utc_now().isoformat(),
            "project": str(BASE),
            "account": connector.account,
            "weekday_utc": utc_now().strftime("%A"),
            "results": results,
        }
        ts = utc_now().strftime("%Y%m%dT%H%M%SZ")
        out = REPORTS_DIR / f"ibkr_market_data_matrix_{ts}.json"
        latest = REPORTS_DIR / "ibkr_market_data_matrix_latest.json"
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        out.write_text(text, encoding="utf-8")
        latest.write_text(text, encoding="utf-8")

        print("IBKR Market Data Matrix")
        print("=" * 60)
        print(f"generated_at: {payload['generated_at']}")
        print(f"account: {payload['account']}")
        print(f"weekday_utc: {payload['weekday_utc']}")
        print("-" * 60)
        for row in results:
            diag = row.get("diagnosis", {})
            print(f"[{row['symbol']}]")
            print(f"  cause: {diag.get('primary_cause_code')} | {diag.get('primary_cause')}")
            print(f"  weekend_factor: {diag.get('weekend_factor')}")
            print(f"  has_any_price: {diag.get('has_any_price')}")
            if row.get("contract"):
                c = row["contract"]
                print(f"  contract: {c.get('localSymbol')} | conId={c.get('conId')} | {c.get('exchange')}")
            rt = row.get("realtime", {})
            dl = row.get("delayed", {})
            print(f"  realtime: statuses={rt.get('statuses')} | price={rt.get('price')}")
            print(f"  delayed: statuses={dl.get('statuses')} | price={dl.get('price')}")
            print("-" * 60)
        print(f"saved_report: {out}")
        print(f"latest_alias: {latest}")
        return 0
    finally:
        await connector.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
