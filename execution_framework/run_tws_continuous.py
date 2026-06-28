"""
run_tws_continuous.py
═══════════════════════════════════════════════════════════════════════════════
长期无人值守跑 IBKR 模拟盘的持续运行入口。

整合：
  - enabled_symbols：只交易账户有权限的 7 个品种（MBT 加密无权限，默认禁用）
  - IBKRSession：错误码处理 + 断线重连 + 对账 + 按 OI 选主力
  - RightSidePipeline：右侧确认 + 硬风控 + 风险约束算手数 + dry-run/真实下单
  - TradeJournal：成交后真实 P&L 回写学习库（SQLite data.db）
  - RuntimeGuardian：心跳 + 死手开关（主循环卡死 → 自动撤单 + 停机 + 告警）

安全：默认 dry-run；--live 仅允许端口 7497（模拟盘）；致命错误/对账失败/心跳超时
都会自动停机并撤单。

用法：
  # 持续 dry-run（推荐先这样跑一两天，观察日志和 KPI）
  python3 execution_framework/run_tws_continuous.py --interval 60

  # 持续真实模拟盘（仅 7497）
  python3 execution_framework/run_tws_continuous.py --live --interval 60

  # 外部巡检主进程是否存活
  python3 execution_framework/run_tws_continuous.py --check-heartbeat
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from enabled_symbols import (ENABLED_SYMBOLS, filter_enabled, rejected,
                             SYMBOL_NOTES)
from ibkr_session import IBKRSession
from ibkr_contract_resolver import IBKRContractResolver, ResolvedContract, FUT_SPECS
from right_side_pipeline import RightSidePipeline
from runtime_guardian import RuntimeGuardian, check_heartbeat
from economic_calendar import EconomicCalendar


BASE = Path(__file__).resolve().parent.parent
RUNTIME_DIR = BASE / "reports" / "runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
HEARTBEAT = RUNTIME_DIR / "heartbeat.json"
CALENDAR_FILE = RUNTIME_DIR / "calendar.json"
JOURNAL_DB = str(BASE / "data.db")          # data.db 便于持久化


def _bars_to_df(bars):
    import pandas as pd
    return pd.DataFrame([{"open": b.open, "high": b.high, "low": b.low,
                          "close": b.close, "volume": getattr(b, "volume", 0) or 0}
                         for b in bars])


def _broker_positions(sess):
    out = {}
    for p in sess.ib.positions():
        sym = p.contract.localSymbol or p.contract.symbol
        out[sym] = out.get(sym, 0.0) + float(p.position)
    return out


def lock_contracts(sess: IBKRSession, resolver: IBKRContractResolver, symbols):
    for sym in symbols:
        try:
            if sym in FUT_SPECS:
                spec = FUT_SPECS[sym]
                con = sess.resolve_front_liquid_future(sym, spec["exchange"], spec["currency"])
                if con is not None:
                    resolver._cache[sym] = ResolvedContract(
                        symbol=sym, sec_type="FUT", con_id=con.conId,
                        exchange=con.exchange or spec["exchange"], currency=con.currency,
                        local_symbol=con.localSymbol,
                        last_trade_date=con.lastTradeDateOrContractMonth,
                        multiplier=str(con.multiplier), raw=con)
                    print(f"  [{sym}] 主力锁定 {con.localSymbol} conId={con.conId}")
            else:
                rc = resolver.resolve(sym)
                print(f"  [{sym}] 解析 conId={rc.con_id} {rc.local_symbol}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [{sym}] 合约解析失败（将跳过该品种）: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7497)
    ap.add_argument("--client-id", type=int, default=22)
    ap.add_argument("--symbols", default=",".join(ENABLED_SYMBOLS),
                    help="默认=全部已启用品种（不含无权限的 MBT）")
    ap.add_argument("--equity", type=float, default=50000.0)
    ap.add_argument("--interval", type=float, default=60.0, help="扫描间隔秒")
    ap.add_argument("--heartbeat-timeout", type=float, default=120.0)
    ap.add_argument("--live", action="store_true", help="真实模拟盘下单（仅 7497）")
    ap.add_argument("--telegram", action="store_true", help="启用 Telegram 告警")
    ap.add_argument("--check-heartbeat", action="store_true",
                    help="只检查主进程是否存活后退出")
    ap.add_argument("--gen-calendar", type=int, default=0, metavar="DAYS",
                    help="生成未来 N 天的默认经济日历后退出（需用官方日期校正）")
    ap.add_argument("--event-window", type=float, default=120.0,
                    help="事件触发窗口秒（事件时点后多少秒内启动冷静期）")
    ap.add_argument("--lead-minutes", type=float, default=15.0,
                    help="会前降温提前量（事件前 N 分钟冻结新入场并平现货持仓）")
    ap.add_argument("--no-pre-flatten", action="store_true",
                    help="会前只冻结新入场，不平掉现货加密持仓")
    ap.add_argument("--broker-source-of-truth", action="store_true",
                    help="对账时以券商当前持仓为准，适合已有 paper 持仓时接管持续运行")
    args = ap.parse_args()

    if args.gen_calendar > 0:
        cal = EconomicCalendar(str(CALENDAR_FILE), enabled_symbols=ENABLED_SYMBOLS)
        cal.load()
        n = cal.generate_default(days=args.gen_calendar)
        print(f"已生成 {n} 个默认事件 -> {CALENDAR_FILE}")
        print("⚠ FOMC/ECB/BOJ 日期不规则，请用官方日历手动校正。")
        return 0

    if args.check_heartbeat:
        print(check_heartbeat(str(HEARTBEAT), args.heartbeat_timeout))
        return 0

    if args.live and args.port != 7497:
        print(f"拒绝：--live 仅允许 7497（模拟盘），当前 {args.port}")
        return 2
    dry = not args.live

    requested = [s.strip().upper().replace("/", "") for s in args.symbols.split(",") if s.strip()]
    symbols = filter_enabled(requested)
    skipped = rejected(requested)
    print(f"启用品种: {symbols}")
    if skipped:
        print(f"已跳过(无权限/禁用): {skipped}  "
              f"（如 MBT 加密货币：{SYMBOL_NOTES.get('MBT','')}）")
    if not symbols:
        print("没有可交易的已启用品种，退出。")
        return 1

    # 连接
    sess = IBKRSession(host=args.host, port=args.port, client_id=args.client_id)
    if not sess.connect():
        print("无法连接 TWS。请确认已开 TWS/Gateway、API 已启用、端口正确。")
        return 1
    print(f"已连接 TWS {args.host}:{args.port} (paper={sess.is_paper}) "
          f"模式={'LIVE-PAPER' if args.live else 'DRY-RUN'}")

    pipe = RightSidePipeline(ib=sess.ib, dry_run=dry, equity=args.equity,
                             log_path=str(RUNTIME_DIR / "continuous.log"),
                             journal_db=JOURNAL_DB)
    pipe.attach_session(sess)

    lock_contracts(sess, pipe.resolver, symbols)

    # 启动对账
    local_positions = {}
    if args.broker_source_of_truth:
        local_positions = _broker_positions(sess)
        if local_positions:
            print(f"已接管券商当前持仓作为本地基准: {local_positions}")

    recon = sess.reconcile(local_positions=local_positions)
    print(f"启动对账 in_sync={recon.in_sync} 券商持仓={recon.broker_positions}")
    if not recon.in_sync:
        pipe.halt("startup_position_desync")

    # 死手开关：心跳超时 → 撤掉所有未结单 + 管线停机 + 告警
    def emergency(why: str):
        try:
            for s in symbols:
                sess.cancel_all_for(s)
        finally:
            pipe.halt(f"dead_man_switch:{why}")

    guardian = RuntimeGuardian(
        heartbeat_path=str(HEARTBEAT), timeout_s=args.heartbeat_timeout,
        on_dead=emergency,
        health_check=lambda: sess.ib.isConnected(),
        on_unhealthy=lambda: sess._schedule_reconnect(),
        telegram=args.telegram)
    guardian.start()

    # 经济日历：加载已有事件表（由 --gen-calendar 生成或外部写入）
    calendar = EconomicCalendar(str(CALENDAR_FILE), enabled_symbols=symbols)
    loaded = calendar.load()
    print(f"经济日历: 已加载 {loaded} 个事件")
    up = calendar.upcoming(datetime.now(timezone.utc), horizon_h=24)
    if up:
        print("  未来24h内事件:")
        for e in up[:8]:
            print(f"    {e.event_time.isoformat()}  {e.name}  -> {e.symbols}")
    else:
        print("  未来24h内无预定事件（可用 --gen-calendar 生成或手动写 calendar.json）。")

    # 优雅退出
    stop_flag = {"stop": False}
    def _sig(_s, _f):
        stop_flag["stop"] = True
        print("\n收到退出信号，正在收尾...")
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    # 现货现价辅助（供软止损与会前平仓共用）
    def _spot_price(s):
        rcx = pipe.resolver.get_cached(s)
        if rcx is None or not rcx.is_locked:
            return 0.0
        t = sess.ib.reqMktData(rcx.raw, snapshot=True)
        sess.ib.sleep(0.8)
        if t.bid and t.ask and t.bid > 0 and t.ask > 0:
            return (float(t.bid) + float(t.ask)) / 2.0
        return float(t.last or t.close or 0.0)

    print(f"进入持续循环，每 {args.interval:.0f}s 扫描一次。Ctrl+C 退出。")
    try:
        while not stop_flag["stop"]:
            now = datetime.now(timezone.utc)
            scanned = 0

            # ①a 会前降温：事件前 lead-minutes 内冻结新入场、平掉现货持仓
            for ev in calendar.imminent(now, lead_minutes=args.lead_minutes):
                affected = [s for s in ev.symbols if s in symbols]
                if affected:
                    rec = pipe.pre_event_cooldown(
                        affected, ev.name,
                        price_func=lambda s: _spot_price(s) if 'BTC' in s else 0.0,
                        flatten=not args.no_pre_flatten)
                    if rec["frozen"]:
                        mins = (ev.event_time - now).total_seconds() / 60.0
                        print(f"  ❄ 会前降温 {ev.name}（{mins:.0f}min后）：冻结 {rec['frozen']}"
                              + (f"，平现货 {len(rec['crypto_flattened'])} 笔" if rec['crypto_flattened'] else ""))
                        guardian.notify(f"会前降温 {ev.name}", str(rec["frozen"]))

            # ①b 日历到点：自动触发事件（解除会前冻结 + 启动冷静期）
            for ev in calendar.pop_due(now, window_s=args.event_window):
                pipe.clear_pre_event_freeze([s for s in ev.symbols if s in symbols])
                for sym in ev.symbols:
                    if sym not in symbols:
                        continue
                    try:
                        rc0 = pipe.resolver.get_cached(sym)
                        if rc0 is None or not rc0.is_locked:
                            continue
                        bars0 = sess.ib.reqHistoricalData(
                            rc0.raw, endDateTime="", durationStr="2 D",
                            barSizeSetting="1 min", whatToShow="TRADES",
                            useRTH=False, formatDate=1)
                        df0 = _bars_to_df(bars0)
                        if len(df0) >= 20:
                            pipe.on_event(sym, ev.name, ev.event_time, df0)
                            print(f"  ⚡ 事件触发 {ev.name} -> {sym}（进入冷静期）")
                            guardian.notify(f"事件触发 {ev.name}", sym)
                    except Exception as exc:  # noqa: BLE001
                        print(f"  [{sym}] 事件触发异常: {exc}")

            # ② 逐品种评估（只有处于活跃事件冷静期的品种会产生信号）
            for sym in symbols:
                if pipe.is_halted:
                    break
                try:
                    rc = pipe.resolver.get_cached(sym)
                    if rc is None or not rc.is_locked:
                        continue
                    bars = sess.ib.reqHistoricalData(
                        rc.raw, endDateTime="", durationStr="2 D",
                        barSizeSetting="1 min", whatToShow="TRADES",
                        useRTH=False, formatDate=1)
                    df = _bars_to_df(bars)
                    if len(df) < 40:
                        continue

                    # 事件由上方日历自动触发；无活跃事件时 evaluate 返回 no_active_event
                    tkr = sess.ib.reqMktData(rc.raw, snapshot=True)
                    sess.ib.sleep(1.0)
                    bid = float(tkr.bid) if tkr.bid and tkr.bid > 0 else None
                    ask = float(tkr.ask) if tkr.ask and tkr.ask > 0 else None

                    res = pipe.step(sym, datetime.now(timezone.utc), df,
                                    bid=bid, ask=ask,
                                    account_state={"equity": args.equity,
                                                   "consec_losses": 0,
                                                   "daily_pnl_pct": 0.0,
                                                   "feed_lag_ms": 80.0},
                                    confirm_live=args.live)
                    if res.get("status") in ("BUY", "SELL"):
                        print(f"  [{sym}] {res['status']} qty={res.get('quantity')} "
                              f"state={res.get('order_state')}")
                        if res.get("client_ref"):
                            pipe.confirm_fill(sym, res["client_ref"])
                    scanned += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"  [{sym}] 扫描异常: {exc}")

            # 软止损检查（现货加密专用：PAXOS 无原生 STP）
            for trig in pipe.om.check_soft_stops(_spot_price):
                print(f"  ⛔ 软止损触发 {trig['symbol']} @ {trig['current']} "
                      f"(止损 {trig['stop_price']}) -> {trig['exit_state']}")
                guardian.notify("软止损触发", f"{trig['symbol']} @ {trig['current']}")
                # 回写真实平仓 P&L 到学习库
                pipe.on_close(trig["symbol"], trig["client_ref"],
                              exit_price=trig["current"], exit_reason="soft_stop")

            # 每轮：心跳 + 周期性对账
            guardian.beat({"scanned": scanned, "halted": pipe.is_halted,
                           "symbols": symbols})
            if args.broker_source_of_truth:
                local_positions = _broker_positions(sess)
            recon = sess.reconcile(local_positions=local_positions)
            if not recon.in_sync:
                pipe.halt("periodic_position_desync")

            # 分段 sleep，便于及时响应退出信号
            slept = 0.0
            while slept < args.interval and not stop_flag["stop"]:
                time.sleep(min(2.0, args.interval - slept))
                slept += 2.0
    finally:
        guardian.stop()
        # 收尾：打印学习库统计
        print("\n=== 学习库统计（真实已平仓交易）===")
        all_stats = pipe.journal_stats()
        print(f"  全部: {all_stats}")
        sess.disconnect()
        print("已断开 TWS。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
