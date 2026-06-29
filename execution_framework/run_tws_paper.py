"""
run_tws_paper.py
═══════════════════════════════════════════════════════════════════════════════
TWS 模拟盘运行入口：把右侧确认管线接到真实 IBKR 模拟盘（端口 7497）。

这是"事件 → 冷静期 → 趋势确认 → (模拟盘)下单 → 止损退出 → 对账 → 日志"闭环的可运行壳。

安全设计：
  - 默认 --dry-run（构造下单意图但不真实发单）。
  - 真实发单需显式 --live，且仍强制要求端口为 7497（模拟盘）；若检测到 7496（实盘）
    会直接拒绝运行，避免误连实盘。
  - 致命 IBKR 错误（200/201/203 等）或持仓对账失败 → 自动 halt，停止新入场。

用法（你已和 TWS 调通后）：
  # 1. 先纯连接 + 合约解析 + 对账自检（不下单）
  python3 execution_framework/run_tws_paper.py --check --symbols MNQ,MES,ZN

  # 2. dry-run 跑一根评估（拉历史1分钟K线，构造下单意图但不发单）
  python3 execution_framework/run_tws_paper.py --dry-run --symbols MNQ

  # 3. 真实模拟盘下单（仅 7497，谨慎）
  python3 execution_framework/run_tws_paper.py --live --symbols MNQ

注意：本文件给出标准接线方式；事件识别、K线拉取频率等可按你的数据源接入。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ibkr_session import IBKRSession
from ibkr_contract_resolver import IBKRContractResolver, ResolvedContract, FUT_SPECS
from right_side_pipeline import RightSidePipeline


def _bars_to_df(bars):
    """ib_insync BarDataList -> DataFrame(open/high/low/close/volume)."""
    import pandas as pd
    rows = [{"open": b.open, "high": b.high, "low": b.low,
             "close": b.close, "volume": getattr(b, "volume", 0) or 0}
            for b in bars]
    return pd.DataFrame(rows)


def _historical_what_to_show(resolved: ResolvedContract) -> str:
    if resolved.sec_type == "CASH":
        return "MIDPOINT"
    if resolved.sec_type == "CRYPTO":
        return "AGGTRADES"
    return "TRADES"


def fetch_1min(ib, resolved: ResolvedContract, lookback="2 D"):
    bars = ib.reqHistoricalData(
        resolved.raw, endDateTime="", durationStr=lookback,
        barSizeSetting="1 min", whatToShow=_historical_what_to_show(resolved),
        useRTH=False, formatDate=1)
    return _bars_to_df(bars), bars


def _broker_positions(sess):
    out = {}
    for p in sess.ib.positions():
        sym = p.contract.localSymbol or p.contract.symbol
        out[sym] = out.get(sym, 0.0) + float(p.position)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7497, help="7497=模拟盘 (强制)")
    ap.add_argument("--client-id", type=int, default=21)
    ap.add_argument("--symbols", default="MNQ", help="逗号分隔，如 MNQ,MES,ZN")
    ap.add_argument("--equity", type=float, default=50000.0)
    ap.add_argument("--check", action="store_true", help="只连接+解析+对账，不评估不下单")
    ap.add_argument("--dry-run", action="store_true", help="评估并构造下单意图，不真实发单")
    ap.add_argument("--live", action="store_true", help="真实模拟盘下单（仅 7497）")
    ap.add_argument("--event", default="CPI")
    ap.add_argument("--broker-source-of-truth", action="store_true",
                    help="对账时以券商当前持仓为基准，适合已有 paper 持仓时接管运行")
    args = ap.parse_args()

    # 安全闸：真实发单只允许 7497 模拟盘
    if args.live and args.port != 7497:
        print(f"拒绝运行：--live 仅允许端口 7497（模拟盘），当前 {args.port}。")
        return 2
    dry = not args.live  # 未显式 --live 一律 dry-run

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    # 连接
    sess = IBKRSession(host=args.host, port=args.port, client_id=args.client_id)
    if not sess.connect():
        print("无法连接 TWS。请确认 TWS/IB Gateway 已开、API 已启用、端口正确。")
        return 1
    print(f"已连接 TWS {args.host}:{args.port} (paper={sess.is_paper})")

    log_dir = Path(__file__).resolve().parent.parent / "reports" / "right_side_runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    pipe = RightSidePipeline(ib=sess.ib, dry_run=dry, equity=args.equity,
                             log_path=str(log_dir / "tws_paper.log"))
    pipe.attach_session(sess)   # 致命错误/重连接到管线 halt

    # 用会话的 OI 选主力，写回 resolver 缓存（取代默认近月）
    resolver: IBKRContractResolver = pipe.resolver
    for sym in symbols:
        try:
            rc = resolver.resolve(sym, refresh=True)
            if sym in FUT_SPECS:
                print(f"  [{sym}] 前月锁定: {rc.local_symbol} "
                      f"(conId={rc.con_id}, exp={rc.last_trade_date})")
            else:
                print(f"  [{sym}] 解析: conId={rc.con_id} {rc.local_symbol}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [{sym}] 解析失败: {exc}")

    # 对账自检
    local_positions = {}
    if args.broker_source_of_truth:
        local_positions = _broker_positions(sess)
        if local_positions:
            print(f"已接管券商当前持仓作为本地基准: {local_positions}")

    recon = sess.reconcile(local_positions=local_positions)
    print(f"对账: in_sync={recon.in_sync}, 券商持仓={recon.broker_positions}, "
          f"未结单={len(recon.open_orders)}")
    if not recon.in_sync:
        pipe.halt("startup_position_desync")

    if args.check:
        sess.disconnect()
        return 0

    # 评估闭环（演示：对每个品种触发事件并评估当前1分钟K线）
    now = datetime.now(timezone.utc)
    for sym in symbols:
        try:
            rc = resolver.get_cached(sym)
            if rc is None or not rc.is_locked:
                print(f"  [{sym}] 未锁定合约，跳过。")
                continue
            df, _ = fetch_1min(sess.ib, rc)
            if len(df) < 40:
                print(f"  [{sym}] K线不足({len(df)})，跳过。")
                continue
            pipe.on_event(sym, args.event, now, df)

            # 取当前盘口
            tkr = sess.ib.reqMktData(rc.raw, snapshot=True)
            sess.ib.sleep(1.2)
            bid = float(tkr.bid) if tkr.bid and tkr.bid > 0 else None
            ask = float(tkr.ask) if tkr.ask and tkr.ask > 0 else None

            res = pipe.step(sym, datetime.now(timezone.utc), df,
                            bid=bid, ask=ask,
                            account_state={"equity": args.equity, "consec_losses": 0,
                                           "daily_pnl_pct": 0.0, "feed_lag_ms": 80.0},
                            confirm_live=args.live)
            print(f"  [{sym}] -> {res.get('status')} | {res.get('reason', res.get('note',''))}")
            if res.get("status") in ("BUY", "SELL") and res.get("client_ref"):
                state = pipe.confirm_fill(sym, res["client_ref"])
                print(f"       order_state={res.get('order_state')} fill_poll={state}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [{sym}] 评估异常: {exc}")

    print("\nKPI:")
    for k, v in pipe.kpi_report()["Right-Side Confirmation Status"].items():
        print(f"  {k}: {v}")

    sess.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
