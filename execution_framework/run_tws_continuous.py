"""
run_tws_continuous.py
═══════════════════════════════════════════════════════════════════════════════
长期无人值守跑 IBKR 模拟盘的持续运行入口。

整合：
  - enabled_symbols：只交易账户有权限的 8 个品种（MBT 加密无权限，默认禁用）
  - IBKRSession：错误码处理 + 断线重连 + 对账 + 按 OI 选主力
  - RightSidePipeline：右侧确认 + 硬风控 + 风险约束算手数 + dry-run/真实下单
  - TradeJournal：成交后真实 P&L 回写学习库（SQLite data.db）
  - RuntimeGuardian：心跳 + 死手开关（主循环卡死 → 自动撤单 + 停机 + 告警）

安全：默认 dry-run；--live 仅允许模拟盘端口 7497（TWS）或 4002（IB Gateway）；
致命错误/对账失败/心跳超时都会自动停机并撤单。

用法：
  # 持续 dry-run（推荐先这样跑一两天，观察日志和 KPI）
  python3 execution_framework/run_tws_continuous.py --interval 60

  # 持续真实模拟盘（7497=TWS paper, 4002=IB Gateway paper）
  python3 execution_framework/run_tws_continuous.py --live --interval 60

  # 外部巡检主进程是否存活
  python3 execution_framework/run_tws_continuous.py --check-heartbeat
"""

from __future__ import annotations

import argparse
import os
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
from right_side_pipeline import RightSidePipeline, DEFAULT_CONTRACT_FEES
from v2_telemetry_shadow import V2TelemetryShadow
from microstructure_shadow import MicrostructureShadow
from timeseries_shadow import TimeSeriesShadow
from news_shadow import NewsShadow
from news_feed import RssNewsFeed
from eia_feed import EiaPetroleumFeed, _enabled_from_env as _eia_enabled
from depth_collector import DepthCollector
from event_data_archive import EventDataArchive
from runtime_guardian import RuntimeGuardian, check_heartbeat
from economic_calendar import EconomicCalendar


BASE = Path(__file__).resolve().parent.parent
RUNTIME_DIR = BASE / "reports" / "runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
HEARTBEAT = RUNTIME_DIR / "heartbeat.json"
CALENDAR_FILE = RUNTIME_DIR / "calendar.json"
JOURNAL_DB = str(BASE / "data.db")          # data.db 便于持久化
SAFETY_DB = str(RUNTIME_DIR / "execution_safety.db")


def _bars_to_df(bars):
    import pandas as pd
    return pd.DataFrame([{"date": getattr(b, "date", None),
                          "open": b.open, "high": b.high, "low": b.low,
                          "close": b.close, "volume": getattr(b, "volume", 0) or 0}
                         for b in bars])


def _historical_what_to_show(resolved: ResolvedContract) -> str:
    """IBKR 历史数据类型按资产切换。

    FX 现货不能稳定使用 TRADES/LAST，改用 MIDPOINT，
    否则会反复触发 FXSUBPIP / no historical market data 警告。
    ZEROHASH 加密现货要求 AGGTRADES，不能用默认 TRADES（Paxos 迁移后同样如此）。
    """
    if resolved.sec_type == "CASH":
        return "MIDPOINT"
    if resolved.sec_type == "CRYPTO":
        return "AGGTRADES"
    return "TRADES"


def _broker_positions(sess):
    out = {}
    for p in sess.ib.positions():
        sym = p.contract.localSymbol or p.contract.symbol
        out[sym] = out.get(sym, 0.0) + float(p.position)
    return out


def _account_risk_snapshot(sess, account_id: str, journal,
                           feed_lag_ms: float = 0.0,
                           book_desync: bool = False):
    """Build hard-risk inputs from broker/account facts; return None if unusable."""
    try:
        values = list(sess.ib.accountValues() or [])
    except Exception:  # noqa: BLE001
        return None
    selected = {}
    for row in values:
        if getattr(row, "account", account_id) not in ("", account_id):
            continue
        tag = str(getattr(row, "tag", "") or "")
        currency = str(getattr(row, "currency", "") or "")
        try:
            value = float(getattr(row, "value", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        # Prefer account base currency, then USD, then any reported currency.
        priority = 2 if currency == "BASE" else (1 if currency == "USD" else 0)
        previous = selected.get(tag)
        if previous is None or priority > previous[0]:
            selected[tag] = (priority, value)
    equity = (selected.get("NetLiquidation") or (0, 0.0))[1]
    if equity <= 0:
        return None
    if "DailyPnL" in selected:
        daily_pnl = selected["DailyPnL"][1]
    else:
        daily_pnl = ((selected.get("RealizedPnL") or (0, 0.0))[1]
                     + (selected.get("UnrealizedPnL") or (0, 0.0))[1])
    positions = _broker_positions(sess)
    return {
        "equity": equity,
        "daily_pnl_pct": daily_pnl / equity,
        "consec_losses": (journal.current_consecutive_losses()
                          if journal is not None else 0),
        "active_position": sum(
            1 for quantity in positions.values() if abs(quantity) > 1e-9),
        "position_pnl_pct": 0.0,
        "feed_lag_ms": float(feed_lag_ms),
        "book_desync": bool(book_desync),
    }


def lock_contracts(sess: IBKRSession, resolver: IBKRContractResolver, symbols):
    for sym in symbols:
        try:
            rc = resolver.resolve(sym, refresh=True)
            if sym in FUT_SPECS:
                print(f"  [{sym}] 前月锁定 {rc.local_symbol} conId={rc.con_id}")
            else:
                print(f"  [{sym}] 解析 conId={rc.con_id} {rc.local_symbol}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [{sym}] 合约解析失败（将跳过该品种）: {exc}")


def _needs_fast_poll(pipe) -> bool:
    """存在事件窗口 / 在途订单 / 未平仓持仓 / 活跃软止损时切高频档。

    核心证据是信息在事件后约 5 分钟内被吸收，60s 固定轮询会错过
    右侧确认窗口和硬封顶/软止损的退出时点；无事件、无订单、无持仓的
    LEARN 等待态则降回低频档，避免对 TWS 空转请求。
    """
    for st in pipe.engine.states.values():
        if getattr(st, "active", False):
            return True
    if pipe.om.pending_tickets():
        return True
    for pos in pipe.lifecycle.positions.values():
        if pos.state != "CLOSED":
            return True
    for ss in pipe.om.soft_stops.values():
        if ss.get("active"):
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--client-id", type=int, default=22)
    ap.add_argument("--symbols", default=",".join(ENABLED_SYMBOLS),
                    help="默认=全部已启用品种（不含无权限的 MBT）")
    ap.add_argument("--equity", type=float, default=50000.0)
    ap.add_argument("--interval", type=float, default=60.0, help="扫描间隔秒（空闲/LEARN 态）")
    ap.add_argument("--fast-interval", type=float, default=2.0,
                    help="事件窗口/在途订单/未平仓持仓时的高频扫描间隔秒（建议 1-5）")
    ap.add_argument("--heartbeat-timeout", type=float, default=120.0)
    ap.add_argument("--live", action="store_true", help="真实模拟盘下单（7497=TWS paper, 4002=IB Gateway paper）")
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
    ap.add_argument("--account-id", default="",
                    help="IBKR 账户号；留空时使用 API 返回的唯一账户")
    ap.add_argument("--strategy-version", default="eventalpha-v3")
    ap.add_argument("--annual-event-limit", type=int, default=15,
                    help="每账户每年最多交易的独立重大事件数；这是上限，不是配额")
    ap.add_argument("--max-products-per-event", type=int, default=1,
                    help="每个重大事件最多允许交易的产品数")
    ap.add_argument("--archive-root", default="",
                    help="可选：保存可重放事件窗口原始流的目录；留空不归档")
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

    if args.live and args.port not in (7497, 4002):
        print(f"拒绝：--live 仅允许模拟盘端口 7497(TWS) 或 4002(IB Gateway)，当前 {args.port}")
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
        print("无法连接 IBKR API。请确认已开 TWS/IB Gateway、API 已启用、端口正确。")
        return 1
    print(f"已连接 IBKR {args.host}:{args.port} (paper={sess.is_paper}) "
          f"模式={'LIVE-PAPER' if args.live else 'DRY-RUN'}")

    managed_accounts = list(sess.ib.managedAccounts() or [])
    if args.account_id:
        if managed_accounts and args.account_id not in managed_accounts:
            print(f"拒绝：指定账户 {args.account_id} 不在 IBKR API 返回账户中。")
            sess.disconnect()
            return 2
        account_id = args.account_id
    elif len(managed_accounts) == 1:
        account_id = managed_accounts[0]
    elif args.live:
        print("拒绝：--live 且 API 返回零个或多个账户时，必须显式提供 --account-id。")
        sess.disconnect()
        return 2
    else:
        account_id = managed_accounts[0] if managed_accounts else "DRYRUN"

    pipe = RightSidePipeline(ib=sess.ib, dry_run=dry, equity=args.equity,
                             log_path=str(RUNTIME_DIR / "continuous.log"),
                             journal_db=JOURNAL_DB,
                             safety_db=SAFETY_DB if args.live else None,
                             account_id=account_id,
                             strategy_version=args.strategy_version,
                             annual_event_limit=args.annual_event_limit,
                             max_products_per_event=args.max_products_per_event,
                             contract_fees=DEFAULT_CONTRACT_FEES,
                             broker_channel=("PAPER" if sess.is_paper else "LIVE"))
    pipe.attach_session(sess)

    lease_owner = f"runner-{os.getpid()}-client-{args.client_id}"
    if pipe.intent_ledger is not None:
        if not pipe.intent_ledger.acquire_lease(
                account_id, lease_owner, ttl_s=max(30.0, args.interval * 3.0)):
            print(f"拒绝：账户 {account_id} 已有另一个有效执行进程。")
            sess.disconnect()
            return 2
        print(f"账户级执行租约已取得: {account_id} owner={lease_owner}")
        # 固定 fencing token：之后每次下单前管线会复核租约未被接管。
        if not pipe.configure_lease_guard(lease_owner):
            print("拒绝：租约已取得但 fencing token 读取失败，为安全起见退出。")
            pipe.intent_ledger.release_lease(account_id, lease_owner)
            sess.disconnect()
            return 2

    # v2 遥测影子记录（observe-only，默认关，EVENTALPHA_V2_TELEMETRY=1 开启）。
    # 只把实时盘口/连接/延迟转成 v2 ExecutionState 并跑执行质量门后落日志，
    # 绝不下单、不改任何交易决策，用于在真实 paper 行情上验证遥测适配器。
    shadow = V2TelemetryShadow(log_path=str(RUNTIME_DIR / "v2_telemetry_shadow.log"))
    if shadow.enabled:
        print("v2 遥测影子记录: 已开启（observe-only，不影响下单）"
              " -> reports/runtime/v2_telemetry_shadow.log")

    # Step 2 · Phase A: microstructure 影子记录（observe-only，默认关，
    # EVENTALPHA_MICROSTRUCTURE_SHADOW=1 开启）。用 reqMktDepth 取 Level-2 买卖量、
    # 用已拉的 1 分钟 bar 近似逐笔 CVD，跑 Step-1 的假冲击/CVD背离/买盘枯竭门只落日志，
    # 绝不下单、不改任何决策。阈值仍是未验证占位，等 Phase C 用这些日志校准。
    micro_shadow = MicrostructureShadow(
        log_path=str(RUNTIME_DIR / "microstructure_shadow.log"))
    depth_collector = DepthCollector()
    event_archive = (EventDataArchive(args.archive_root, source="IBKR_PAPER_API")
                     if args.archive_root else None)
    sealed_event_archives = set()
    if micro_shadow.enabled:
        print("microstructure 影子记录: 已开启（observe-only，不影响下单）"
              " -> reports/runtime/microstructure_shadow.log")

    # Step 2 · Phase D: 零样本时序确认影子（observe-only，默认关，
    # EVENTALPHA_TIMESERIES_SHADOW=1 开启）。用已拉的历史收盘价喂预训练零样本模型
    # （Chronos，未装则降级 naive 基线并如实标注 backend），记录"模型会确认还是否决"
    # 信号方向，只落日志，绝不下单、不改任何决策。阈值仍是未验证占位，等 Phase C 校准。
    ts_shadow = TimeSeriesShadow(
        log_path=str(RUNTIME_DIR / "timeseries_shadow.log"))
    if ts_shadow.enabled:
        print("timeseries 影子记录: 已开启（observe-only，不影响下单）"
              " -> reports/runtime/timeseries_shadow.log")

    # Step 2 · Phase E: LLM 新闻网关影子（observe-only，默认关，
    # EVENTALPHA_NEWS_SHADOW=1 开启）。对日历/新闻条目做事件分类 + 风险情绪 + 置信度，
    # 记录"若开会不会唤醒"，只落日志，绝不下单。LLM 后端懒加载（有 key 才用，没 key
    # 降级关键词基线并如实标注 backend）。唤醒阈值仍是未验证占位，等 Phase C 校准。
    news_shadow = NewsShadow(
        log_path=str(RUNTIME_DIR / "news_shadow.log"),
        enabled_symbols=symbols)
    news_feed = RssNewsFeed() if news_shadow.enabled else None
    # Phase E-3: EIA weekly crude-inventory feed. Default OFF; only built when
    # EVENTALPHA_EIA_FEED is set AND a free EIA_API_KEY is present (no key => the
    # feed yields nothing, never an error). observe-only.
    eia_feed = (EiaPetroleumFeed()
                if (news_shadow.enabled and _eia_enabled()) else None)
    if news_shadow.enabled:
        print("news 影子记录: 已开启（observe-only，不影响下单）"
              " -> reports/runtime/news_shadow.log")
        if news_feed is not None:
            print(f"news RSS 源: {len(news_feed.feeds)} 个 -> "
                  + ", ".join(news_feed.feeds))
        if eia_feed is not None:
            has_key = bool(eia_feed.api_key)
            print(f"news EIA 源: 已开启（原油周度库存） key={'已配' if has_key else '缺失→不会产出'}")

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
        telegram=False)
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


    def _quote_snapshot_needed(pipe: RightSidePipeline, symbol: str) -> bool:
        """只有在活跃事件窗口内才去拉盘口快照。

        在 no_active_event 的等待态，每轮请求 futures 快照只会制造
        订阅/延迟数据 warning，对实际交易决策没有价值。
        """
        state = pipe.engine.states.get(symbol)
        if state is None or not state.active:
            return False
        if state.confirmed_pending:
            return False
        return True

    fast_poll_state = {"fast": None}   # None = 尚未打印过档位
    print(f"进入持续循环，空闲每 {args.interval:.0f}s、事件窗口每 "
          f"{args.fast_interval:.1f}s 扫描一次。Ctrl+C 退出。")
    try:
        while not stop_flag["stop"]:
            now = datetime.now(timezone.utc)
            scanned = 0
            if pipe.intent_ledger is not None:
                renewed = pipe.intent_ledger.renew_lease(
                    account_id, lease_owner,
                    ttl_s=max(30.0, args.interval * 3.0))
                if not renewed:
                    pipe.halt("account_execution_lease_lost")
                    stop_flag["stop"] = True
                    continue
            account_risk = _account_risk_snapshot(
                sess, account_id, pipe.journal, feed_lag_ms=0.0)
            if account_risk is None:
                if args.live:
                    pipe.halt("broker_account_snapshot_unavailable")
                    stop_flag["stop"] = True
                    continue
                account_risk = {
                    "equity": args.equity, "daily_pnl_pct": 0.0,
                    "consec_losses": 0, "active_position": 0,
                    "position_pnl_pct": 0.0, "feed_lag_ms": 0.0,
                    "book_desync": False,
                }

            # 持续推进订单状态；不能只在提交后的同一毫秒轮询一次。
            for pending in pipe.om.pending_tickets():
                try:
                    pipe.confirm_fill(pending.symbol, pending.client_ref)
                except Exception as _pexc:  # noqa: BLE001
                    print(f"  [{pending.symbol}] 订单状态轮询异常: {_pexc}")

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
                            barSizeSetting="1 min", whatToShow=_historical_what_to_show(rc0),
                            useRTH=False, formatDate=1)
                        df0 = _bars_to_df(bars0)
                        if len(df0) >= 20:
                            event_id = f"{ev.name}@{ev.event_time.isoformat()}"
                            pipe.on_event(
                                sym, ev.name, ev.event_time, df0,
                                event_id=event_id)
                            if event_archive is not None:
                                event_archive.open_event(
                                    event_id, ev.name, ev.event_time, sym,
                                    {
                                        "conId": rc0.con_id,
                                        "localSymbol": rc0.local_symbol,
                                        "secType": rc0.sec_type,
                                        "exchange": rc0.exchange,
                                        "currency": rc0.currency,
                                        "multiplier": rc0.multiplier,
                                        "whatToShow": _historical_what_to_show(rc0),
                                    },
                                    extra={"bar_size": "1 min",
                                           "useRTH": False})
                                pre_rows = []
                                for row in df0.tail(120).to_dict("records"):
                                    pre_rows.append({
                                        "bar_time": str(row.get("date") or ""),
                                        "open": float(row["open"]),
                                        "high": float(row["high"]),
                                        "low": float(row["low"]),
                                        "close": float(row["close"]),
                                        "volume": float(row.get("volume") or 0.0),
                                        "phase": "trigger_snapshot",
                                    })
                                event_archive.append_many(
                                    event_id, sym, "bars", pre_rows, now)
                            print(f"  ⚡ 事件触发 {ev.name} -> {sym}（进入冷静期）")
                    except Exception as exc:  # noqa: BLE001
                        print(f"  [{sym}] 事件触发异常: {exc}")

            # ①c Phase E: 新闻网关影子（observe-only）。对未来 24h 的日历事件做
            # 分类/情绪/唤醒判定，只落日志（按 item_id 去重，同一事件只记一次）。
            if news_shadow.enabled:
                try:
                    for ev in calendar.upcoming(now, horizon_h=24):
                        _txt = ev.title or ev.name
                        _eid = f"{ev.name}@{ev.event_time.isoformat()}"
                        news_shadow.observe(_txt, item_id=_eid, source="calendar")
                except Exception as _nexc:  # noqa: BLE001
                    print(f"  news影子异常: {_nexc}")

            # ①d Phase E-2: 实时 RSS 新闻源。每轮抓新标题喂网关（按 item_id 去重，
            # 稳态下只有真·新标题才会触发一次 LLM 调用，成本极低）。observe-only。
            if news_shadow.enabled and news_feed is not None:
                try:
                    for it in news_feed.fetch(max_items=12):
                        _ntxt = (it.title + (". " + it.summary if it.summary else "")).strip()
                        news_shadow.observe(_ntxt, item_id=it.item_id, source="rss")
                except Exception as _fexc:  # noqa: BLE001
                    print(f"  news RSS 影子异常: {_fexc}")

            # ①e Phase E-3: EIA 原油周度库存。结构化 build/draw 头条喂网关（按发布周
            # 去重，一周只记一次）。observe-only；无 key 时静默不产出。
            if news_shadow.enabled and eia_feed is not None:
                try:
                    for it in eia_feed.fetch(max_items=1):
                        news_shadow.observe(it.title, item_id=it.item_id, source="eia")
                except Exception as _eexc:  # noqa: BLE001
                    print(f"  news EIA 影子异常: {_eexc}")

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
                        barSizeSetting="1 min", whatToShow=_historical_what_to_show(rc),
                        useRTH=False, formatDate=1)
                    df = _bars_to_df(bars)
                    if len(df) < 40:
                        continue

                    bid = None
                    ask = None
                    _tkr = None
                    if _quote_snapshot_needed(pipe, sym):
                        # 只有在可能进入真实右侧确认时才拉盘口，避免 idle 态制造 warning。
                        tkr = sess.ib.reqMktData(rc.raw, snapshot=True)
                        sess.ib.sleep(1.0)
                        _tkr = tkr
                        bid = float(tkr.bid) if tkr.bid and tkr.bid > 0 else None
                        ask = float(tkr.ask) if tkr.ask and tkr.ask > 0 else None

                    # v2 遥测影子记录（仅在已开启且已取到盘口时；observe-only）。
                    if shadow.enabled and _tkr is not None:
                        _bs = float(_tkr.bidSize) if getattr(_tkr, "bidSize", None) else None
                        _as = float(_tkr.askSize) if getattr(_tkr, "askSize", None) else None
                        _te = (_tkr.time.timestamp()
                               if getattr(_tkr, "time", None) else None)
                        shadow.observe(sym, connected=sess.ib.isConnected(),
                                       bid=bid, ask=ask, bid_size=_bs, ask_size=_as,
                                       latency_s=0.080, tick_epoch=_te)

                    # Step 2 · Phase A: microstructure 影子（observe-only）。
                    # 取 Level-2 深度 + bar 近似 tape，记录 Step-1 门"若开会怎么判"。
                    _bsz = None
                    _asz = None
                    if micro_shadow.enabled or pipe.engine.fakeout_filter_enabled:
                        try:
                            _bsz, _asz = depth_collector.fetch_depth(
                                sess.ib, rc.raw, sym)
                            depth_collector.update_tape_from_df(sym, df)
                            if micro_shadow.enabled:
                                _closes = df["close"].tolist()
                                _ref = _closes[-min(len(_closes), 10)]
                                _dir = "long" if _closes[-1] >= _ref else "short"
                                _raw = depth_collector.raw_for_exit(sym)
                                micro_shadow.observe(
                                    sym, _dir, _bsz, _asz,
                                    recent_prices=_raw["recent_prices"],
                                    recent_volumes=_raw["recent_volumes"],
                                    near_side_size_series=_raw["near_side_size_series"],
                                    tape_source=_raw["tape_source"])
                        except Exception as _mexc:  # noqa: BLE001
                            print(f"  [{sym}] microstructure影子异常: {_mexc}")

                    # Step 2 · Phase D: 零样本时序确认影子（observe-only）。
                    # 用历史收盘价问预训练模型"下 H 根是否顺信号方向"，只落日志。
                    if ts_shadow.enabled:
                        try:
                            _tcloses = df["close"].tolist()
                            _tref = _tcloses[-min(len(_tcloses), 10)]
                            _tdir = "long" if _tcloses[-1] >= _tref else "short"
                            ts_shadow.observe(sym, _tdir, _tcloses,
                                              source="bar_close")
                        except Exception as _texc:  # noqa: BLE001
                            print(f"  [{sym}] timeseries影子异常: {_texc}")

                    # 可选的可重放事件档案。只在事件活跃时保存原始观察，
                    # 不保存模型判断，避免用派生信号冒充市场数据。
                    _event_state = pipe.engine.states.get(sym)
                    if (event_archive is not None and _event_state is not None
                            and _event_state.active and _event_state.event_id):
                        _last = df.iloc[-1]
                        event_archive.append(
                            _event_state.event_id, sym, "bars",
                            {"bar_time": str(_last.get("date") or ""),
                             "open": float(_last["open"]),
                             "high": float(_last["high"]),
                             "low": float(_last["low"]),
                             "close": float(_last["close"]),
                             "volume": float(_last.get("volume", 0.0) or 0.0),
                             "bar_size": "1 min"},
                            datetime.now(timezone.utc))
                        if _tkr is not None:
                            event_archive.append(
                                _event_state.event_id, sym, "l1",
                                {"bid": bid, "ask": ask,
                                 "bid_size": (float(_tkr.bidSize)
                                              if getattr(_tkr, "bidSize", None) else None),
                                 "ask_size": (float(_tkr.askSize)
                                              if getattr(_tkr, "askSize", None) else None),
                                 "ticker_time": str(getattr(_tkr, "time", "") or "")},
                                datetime.now(timezone.utc))
                        _depth_snapshot = depth_collector.last_depth_snapshot(sym)
                        if _depth_snapshot is not None:
                            event_archive.append(
                                _event_state.event_id, sym, "l2",
                                _depth_snapshot, datetime.now(timezone.utc))

                    res = pipe.step(sym, datetime.now(timezone.utc), df,
                                    bid=bid, ask=ask,
                                    bid_sizes=_bsz, ask_sizes=_asz,
                                    account_state=account_risk,
                                    confirm_live=args.live)
                    if res.get("status") in ("BUY", "SELL"):
                        print(f"  [{sym}] {res['status']} qty={res.get('quantity')} "
                              f"state={res.get('order_state')}")
                        if res.get("client_ref"):
                            pipe.confirm_fill(sym, res["client_ref"])
                    scanned += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"  [{sym}] 扫描异常: {exc}")

            if event_archive is not None:
                for sym, state in pipe.engine.states.items():
                    archive_key = (state.event_id, sym)
                    if (state.event_id and not state.active
                            and archive_key not in sealed_event_archives):
                        event_archive.seal_event(state.event_id, sym)
                        sealed_event_archives.add(archive_key)

            # 软止损检查（现货加密专用：ZEROHASH 无原生 STP）
            for trig in pipe.om.check_soft_stops(_spot_price):
                print(f"  ⛔ 软止损触发 {trig['symbol']} @ {trig['current']} "
                      f"(止损 {trig['stop_price']}) -> {trig['exit_state']}")
                # 回写真实平仓 P&L 到学习库
                if trig["exit_state"] == "DRYRUN_SOFT_STOP":
                    pipe.on_close(trig["symbol"], trig["client_ref"],
                                  exit_price=trig["current"], exit_reason="soft_stop")
                else:
                    print("    退出单已发送，等待券商成交确认；未提前记作 CLOSED。")

            # 每轮：心跳 + 周期性对账
            guardian.beat({"scanned": scanned, "halted": pipe.is_halted,
                           "symbols": symbols})
            if args.broker_source_of_truth:
                local_positions = _broker_positions(sess)
            recon = sess.reconcile(local_positions=local_positions)
            if not recon.in_sync:
                pipe.halt("periodic_position_desync")

            # 自适应轮询档位：事件窗口/在途订单/持仓存在时高频，
            # 空闲（LEARN 等待态）降回低频；档位切换时落一行日志。
            fast = _needs_fast_poll(pipe)
            if fast != fast_poll_state["fast"]:
                mode = "高频" if fast else "低频"
                secs = args.fast_interval if fast else args.interval
                print(f"  ⏱ 轮询档位 -> {mode} ({secs:.1f}s)")
                fast_poll_state["fast"] = fast
            sleep_s = max(1.0, args.fast_interval) if fast else args.interval

            # 分段 sleep，便于及时响应退出信号
            slept = 0.0
            while slept < sleep_s and not stop_flag["stop"]:
                time.sleep(min(2.0, sleep_s - slept))
                slept += 2.0
    finally:
        guardian.stop()
        if pipe.intent_ledger is not None:
            pipe.intent_ledger.release_lease(account_id, lease_owner)
        # 收尾：打印学习库统计
        print("\n=== 学习库统计（真实已平仓交易）===")
        all_stats = pipe.journal_stats()
        print(f"  全部: {all_stats}")
        sess.disconnect()
        print("已断开 TWS。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
