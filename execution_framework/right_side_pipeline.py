"""
right_side_pipeline.py
═══════════════════════════════════════════════════════════════════════════════
把右侧确认引擎接入"共享硬风控 + 仓位计算器 + 订单管理"的完整闭环。

这正是审计里最重要的修复点：
  原仓库的好风控（HardStopController / CorrectPositionSizer / StrategyEvaluator）
  没有被各模型调用。本管线把它们设为下单前的【强制串联门】：

  事件 -> 右侧确认(RightSideEventEngine)
       -> 硬风控(HardStopController：日亏/连亏/延迟/点差爆炸 等 8 条硬规则)
       -> 仓位计算(CorrectPositionSizer：风险预算/流动性/滑点/延迟/尾部 五约束取最小)
       -> 合约解析(IBKRContractResolver：锁 conId，禁用 CONTFUT 下单)
       -> 订单管理(IBKROrderManager：marketable-limit + OCA + 成交确认 + 去重)
       -> 结构化日志（生成 Right-Side KPI 字段）

手数不再写死 quantity=1，而是由 CorrectPositionSizer 依据风险约束算出。

默认 dry_run=True，绝不真实发单。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from event_right_side_engine import RightSideEventEngine, DEFAULT_RULES
from ibkr_contract_resolver import IBKRContractResolver, ContractResolutionError
from ibkr_order_manager import IBKROrderManager
from intent_ledger import IntentLedger
from position_lifecycle import PositionLifecycleMonitor
from trade_journal import TradeJournal, TradeRecord
from trade_telegram_notifier import TradeTelegramNotifier

# 共享风控/仓位（容错导入：缺失时降级为安全默认，但会在日志里标记）
_SHARED_OK = True
try:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from shared_quant_core import CorrectPositionSizer
    from shared_risk_guard import HardStopController, AccountRiskState
except Exception:                       # noqa: BLE001
    _SHARED_OK = False
    CorrectPositionSizer = None
    HardStopController = None
    AccountRiskState = None


# ── KPI 计数器（生成报告新增字段的数据源）────────────────────────────────────
class RightSideKPI:
    def __init__(self) -> None:
        self.active_events = 0
        self.cooldown_active = 0
        self.atr_whipsaw_finished = 0
        self.body_breakout_passed = 0
        self.shadow_filter_passed = 0
        self.volume_filter_passed = 0
        self.spread_filter_passed = 0
        self.slippage_filter_passed = 0
        self.orders_blocked_by_risk = 0
        self.orders_ready_for_ibkr = 0

    def as_dict(self) -> Dict[str, int]:
        return {
            "Active Events": self.active_events,
            "Cooldown Active": self.cooldown_active,
            "ATR Whipsaw Finished": self.atr_whipsaw_finished,
            "Body Breakout Passed": self.body_breakout_passed,
            "Shadow Filter Passed": self.shadow_filter_passed,
            "Volume Filter Passed": self.volume_filter_passed,
            "Spread Filter Passed": self.spread_filter_passed,
            "Slippage Filter Passed": self.slippage_filter_passed,
            "Orders Blocked By Risk": self.orders_blocked_by_risk,
            "Orders Ready For IBKR": self.orders_ready_for_ibkr,
        }


class RightSidePipeline:
    def __init__(self, ib=None, dry_run: bool = True,
                 equity: float = 50000.0, max_loss_pct: float = 0.0025,
                 log_path: Optional[str] = None, journal_db: Optional[str] = None,
                 selectivity_enabled: Optional[bool] = None,
                 fakeout_filter_enabled: Optional[bool] = None,
                 fakeout_require_book: Optional[bool] = None,
                 safety_db: Optional[str] = None,
                 account_id: str = "PAPER",
                 strategy_version: str = "eventalpha-v3",
                 annual_event_limit: int = 15,
                 max_products_per_event: int = 1,
                 lifecycle_db: Optional[str] = None,
                 contract_fees: Optional[Dict[str, float]] = None):
        # Opt-in selectivity gate: default OFF; enable via arg or
        # EVENTALPHA_SELECTIVITY=1 (paper first). See event_right_side_engine.
        if selectivity_enabled is None:
            selectivity_enabled = os.environ.get(
                "EVENTALPHA_SELECTIVITY", "").lower() in {"1", "true", "yes", "on"}
        # Opt-in fakeout (false-breakout / OBI) filter: default OFF; enable via arg
        # or EVENTALPHA_FAKEOUT_FILTER=1 (paper first). No-op without Level-2 sizes.
        # Thresholds are UNVALIDATED placeholders pending Step-2 calibration.
        if fakeout_filter_enabled is None:
            fakeout_filter_enabled = os.environ.get(
                "EVENTALPHA_FAKEOUT_FILTER", "").lower() in {"1", "true", "yes", "on"}
        if fakeout_require_book is None:
            fakeout_require_book = os.environ.get(
                "EVENTALPHA_FAKEOUT_REQUIRE_BOOK", "").lower() in {"1", "true", "yes", "on"}
        self.engine = RightSideEventEngine(DEFAULT_RULES,
                                           selectivity_enabled=selectivity_enabled,
                                           fakeout_filter_enabled=fakeout_filter_enabled,
                                           fakeout_require_book=fakeout_require_book)
        self.resolver = IBKRContractResolver(ib)
        self.om = IBKROrderManager(ib, dry_run=dry_run)
        self.kpi = RightSideKPI()
        self.journal = TradeJournal(journal_db) if journal_db else None
        self.equity = equity
        self.max_loss_pct = max_loss_pct
        self.dry_run = dry_run or ib is None
        self.log_path = Path(log_path) if log_path else None
        self.shared_ok = _SHARED_OK
        self._halted = False
        self._halt_reason = ""
        self._pre_event_frozen: set = set()   # 会前冻结的品种（禁新入场）
        self.trade_notifier = TradeTelegramNotifier(enabled=True)
        self.intent_ledger = IntentLedger(safety_db) if safety_db else None
        # 持仓生命周期持久化：默认落在 safety_db 旁边的 .lifecycle.db，
        # 进程崩溃/重启后硬封顶时钟不丢失（此前只在内存，重启即清零）。
        if lifecycle_db is None and safety_db:
            lifecycle_db = str(Path(safety_db).with_suffix(".lifecycle.db"))
        self.lifecycle = PositionLifecycleMonitor(persist_path=lifecycle_db)
        # Fencing-token 守卫：由 runner 在取得账户租约后调用
        # configure_lease_guard() 启用；启用后每次下单前校验 token 未过期、
        # 未被其他进程接管，防止停顿进程苏醒后继续发单（split-brain）。
        self._lease_owner: Optional[str] = None
        self._fencing_token: Optional[int] = None
        self.account_id = account_id
        self.strategy_version = strategy_version
        self.annual_event_limit = int(annual_event_limit)
        self.max_products_per_event = int(max_products_per_event)
        # 单边每手费用表（symbol -> 账户货币），用于 journal 产出净 R；
        # 未配置的品种按 0.0 计（此时净 R 退化为毛 R，统计里可区分）。
        self.contract_fees = dict(contract_fees or {})

        if _SHARED_OK:
            self.hard_stop = HardStopController(
                asset_class="CRYPTO", max_loss_pct=0.01,
                daily_loss_limit_pct=0.015, max_consec_losses=3)
        else:
            self.hard_stop = None

    # ── 日志 ──────────────────────────────────────────────────────────────
    def _log(self, record: Dict[str, Any]) -> None:
        record["ts"] = datetime.now(timezone.utc).isoformat()
        if self.log_path:
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    # ── 停机闸 ──────────────────────────────────────────────────────────────
    def halt(self, reason: str) -> None:
        """致命错误/对账失败时调用：停止一切新入场。"""
        self._halted = True
        self._halt_reason = reason
        self._log({"stage": "HALT", "reason": reason})
        try:
            print(f"\u26d4 PIPELINE HALTED: {reason}")
        except Exception:  # noqa: BLE001
            pass

    # ── 会前降温：重大事件前 5-15 分钟降低/平掉现有持仓 ──────────────
    def pre_event_cooldown(self, symbols, event_name: str,
                           price_func=None, flatten: bool = True) -> dict:
        """在事件前对受影响品种降温：
          1. 冻结该品种新入场（避免在会前低流动性宽点差窗口进场）。
          2. 现货加密：若有软止损持仓且 flatten=True，发市价/IOC 平仓（会前不裸持）。
          3. 期货/外汇：撤掉该品种未结工作单（保护单仍在交易所，不变）。
        返回：{frozen:[...], crypto_flattened:[...]}。会前冻结会在事件触发后自动解除。"""
        frozen, flat = [], []
        for sym in symbols:
            self._pre_event_frozen.add(sym)
            frozen.append(sym)
            # 现货加密软止损持仓：会前主动平仓
            for ref, ss in list(self.om.soft_stops.items()):
                if ss.get("active") and ss["symbol"] == sym and flatten:
                    px = 0.0
                    if price_func:
                        try:
                            px = float(price_func(sym))
                        except Exception:  # noqa: BLE001
                            px = 0.0
                    ss["active"] = False
                    state = self.om._soft_stop_exit(ref, ss, px or ss["stop_price"])
                    if self.journal is not None and px > 0:
                        self.on_close(sym, ref, exit_price=px,
                                      exit_reason=f"pre_event_{event_name}")
                    flat.append({"symbol": sym, "client_ref": ref, "exit": state})
            # 期货/外汇：撤掉该品种未成交工作单（不动交易所保护单）
            try:
                self.om.cancel_all_for(sym)
            except Exception:  # noqa: BLE001
                pass
        rec = {"frozen": frozen, "crypto_flattened": flat, "event": event_name}
        self._log({"stage": "pre_event_cooldown", **rec})
        return rec

    def clear_pre_event_freeze(self, symbols=None) -> None:
        """事件触发后解除会前冻结（以便进入正常的冷静期→右侧确认流程）。"""
        if symbols is None:
            self._pre_event_frozen.clear()
        else:
            for s in symbols:
                self._pre_event_frozen.discard(s)

    @property
    def is_halted(self) -> bool:
        return self._halted

    def attach_session(self, session) -> None:
        """把 TWS 会话的致命错误/重连回调接到本管线。"""
        session.on_fatal = lambda code, msg: self.halt(f"ibkr_fatal_{code}:{msg}")
        session.on_reconnect = lambda: self._log({"stage": "reconnected"})

    # ── Fencing-token 守卫 ────────────────────────────────────────────────
    def configure_lease_guard(self, lease_owner: str) -> bool:
        """在取得账户级执行租约后启用 fencing 校验。

        从 ledger 读当前 fencing epoch 并固定下来；之后 step() 每次下单前
        用 check_fencing 复核：租约被其他进程接管、或本进程停顿超过 TTL 后
        租约过期，epoch 都会失配，下单被拒绝并触发 halt。
        """
        if self.intent_ledger is None:
            return False
        token = self.intent_ledger.current_fencing_token(
            self.account_id, lease_owner)
        if token is None:
            return False
        self._lease_owner = lease_owner
        self._fencing_token = token
        self._log({"stage": "lease_guard_enabled",
                   "owner": lease_owner, "fencing_token": token})
        return True

    # ── 触发事件 ──────────────────────────────────────────────────────────
    def on_event(self, symbol: str, event_name: str, event_time, df,
                 event_id: Optional[str] = None) -> None:
        self.engine.trigger_event(
            symbol, event_name, event_time, df, event_id=event_id)
        self.kpi.active_events += 1
        st = self.engine.states.get(symbol)
        self._log({"stage": "event_triggered", "symbol": symbol,
                   "event": event_name,
                   "event_id": st.event_id if st else event_id})

    # ── 每根K线评估 + 风控 + 仓位 + 下单意图 ──────────────────────────────
    def step(self, symbol: str, now, df, bid=None, ask=None,
             bid_sizes=None, ask_sizes=None,
             account_state: Optional[Dict[str, Any]] = None,
             available_depth: float = 5_000_000.0,
             confirm_live: bool = False) -> Dict[str, Any]:
        # 停机闸：致命错误/对账失败后不再新入场
        if self._halted:
            return {"status": "HOLD", "reason": f"halted:{self._halt_reason}", "symbol": symbol}

        # 会前冻结：重大事件前的品种不准新入场
        if symbol in self._pre_event_frozen:
            return {"status": "HOLD", "reason": "pre_event_frozen", "symbol": symbol}

        # 单品种互斥：已有在途/持仓则不再发新单
        if self.om.has_open(symbol):
            return {"status": "HOLD", "reason": "symbol_has_open_order", "symbol": symbol}

        signal = self.engine.evaluate(symbol, now, df, bid=bid, ask=ask,
                                      bid_sizes=bid_sizes, ask_sizes=ask_sizes)
        self._tally(signal)

        if signal["status"] not in ("BUY", "SELL"):
            self._log({"stage": "evaluate", **signal})
            return signal

        # ── 强制串联硬风控 ────────────────────────────────────────────────
        if self.hard_stop is not None and account_state is not None:
            state = AccountRiskState(
                equity=account_state.get("equity", self.equity),
                daily_pnl_pct=account_state.get("daily_pnl_pct", 0.0),
                consec_losses=account_state.get("consec_losses", 0),
                active_position=account_state.get("active_position", 0),
                position_pnl_pct=account_state.get("position_pnl_pct", 0.0),
                feed_lag_ms=account_state.get("feed_lag_ms", 0.0),
                book_desync=account_state.get("book_desync", False))
            decision = self.hard_stop.check(state)
            if decision.action != "HOLD" or not decision.allow_new_entry:
                self.kpi.orders_blocked_by_risk += 1
                self._log({"stage": "hard_stop_block", "symbol": symbol,
                           "reason": decision.reason, "message": decision.message})
                self.engine.mark_abandoned(symbol, f"hard_stop:{decision.reason}")
                return {"status": "HOLD", "reason": f"hard_stop_{decision.reason}",
                        "symbol": symbol, "detail": decision.message}

        # ── 先解析合约，再按真实 multiplier 做仓位换算 ──────────────────────
        try:
            rc = self.resolver.resolve(symbol)
        except ContractResolutionError as exc:
            self.kpi.orders_blocked_by_risk += 1
            self.engine.mark_abandoned(symbol, f"contract:{exc}")
            self._log({"stage": "contract_unresolved", "symbol": symbol, "error": str(exc)})
            return {"status": "HOLD", "reason": "contract_unresolved",
                    "symbol": symbol, "error": str(exc)}

        # ── 仓位由风险约束决定（不再写死 1 手）──────────────────────────────
        entry = signal["entry_price"]
        stop = signal["stop_loss"]
        tick = signal["tick_size"]
        plan_stop_pct = abs(entry - stop) / entry if entry else 0.0
        contracts = 1.0
        multiplier = 1.0
        sizing_detail: Dict[str, Any] = {"fallback": "shared_core_unavailable"}

        if _SHARED_OK and plan_stop_pct > 0:
            multiplier = 1.0
            if getattr(rc, "sec_type", "") == "FUT":
                try:
                    multiplier = float(rc.multiplier)
                except (TypeError, ValueError):
                    multiplier = 0.0
                if multiplier <= 0:
                    self.engine.mark_abandoned(symbol, "invalid_futures_multiplier")
                    return {"status": "HOLD", "reason": "invalid_futures_multiplier",
                            "symbol": symbol}
            sizer = CorrectPositionSizer(
                equity=self.equity, max_loss_pct=self.max_loss_pct,
                contract_value=max(entry * multiplier, 1.0))
            res = sizer.compute(
                plan_stop_pct=plan_stop_pct,
                pred_slippage_pct=(tick * 3) / entry if entry else 0.0004,
                available_depth=available_depth,
                asset_class=_asset_class_for(signal.get("asset_class", "")))
            contracts = max(0.0, float(res.final_contracts))
            sizing_detail = {"binding": res.binding_constraint,
                             "notional": res.final_notional,
                             "effective_stop_pct": res.effective_stop_width,
                             "contract_multiplier": multiplier,
                             "contract_value": entry * multiplier}

        if contracts <= 0:
            self.kpi.orders_blocked_by_risk += 1
            self.engine.mark_abandoned(symbol, "zero_size")
            self._log({"stage": "size_zero", "symbol": symbol, **sizing_detail})
            return {"status": "HOLD", "reason": "risk_sized_to_zero",
                    "symbol": symbol, "sizing": sizing_detail}

        # ── 下单意图（默认 dry-run）────────────────────────────────────────
        action = "BUY" if signal["status"] == "BUY" else "SELL"
        intent_id = None
        if self.intent_ledger is not None:
            st = self.engine.states.get(symbol)
            if st is None or not st.event_id:
                self.engine.mark_abandoned(symbol, "missing_event_id")
                return {"status": "HOLD", "reason": "missing_event_id",
                        "symbol": symbol}
            event_year = int(st.event_time.year)
            event_res = self.intent_ledger.reserve_event(
                self.account_id, st.event_id, event_year,
                annual_limit=self.annual_event_limit)
            if not event_res.accepted:
                self.engine.mark_abandoned(symbol, event_res.reason)
                self._log({"stage": "event_budget_block", "symbol": symbol,
                           "event_id": st.event_id, "reason": event_res.reason,
                           "counted_events": event_res.counted_events,
                           "annual_limit": event_res.annual_limit})
                return {"status": "HOLD", "reason": event_res.reason,
                        "symbol": symbol}
            intent_res = self.intent_ledger.reserve_intent(
                self.account_id, st.event_id, event_year, symbol, action,
                self.strategy_version,
                max_intents_per_event=self.max_products_per_event)
            if not intent_res.accepted:
                if event_res.reason == "reserved":
                    self.intent_ledger.release_untraded_event(
                        self.account_id, st.event_id, event_year)
                self.engine.mark_abandoned(symbol, intent_res.reason)
                self._log({"stage": "intent_block", "symbol": symbol,
                           "event_id": st.event_id,
                           "intent_id": intent_res.intent_id,
                           "reason": intent_res.reason})
                return {"status": "HOLD", "reason": intent_res.reason,
                        "symbol": symbol}
            intent_id = intent_res.intent_id

            # ── Fencing token：真正发单前确认本进程仍是唯一有效 leader ─────
            # 进程停顿超过租约 TTL 后，另一进程可接管租约（epoch +1）；本进程
            # 苏醒时持有的旧 token 在此失配，拒绝下单并停机，堵住 split-brain。
            if self._lease_owner is not None and not self.intent_ledger.check_fencing(
                    self.account_id, self._lease_owner,
                    self._fencing_token if self._fencing_token is not None else -1):
                self.intent_ledger.advance_intent(intent_id, "CANCELLED")
                if event_res.reason == "reserved":
                    self.intent_ledger.release_untraded_event(
                        self.account_id, st.event_id, event_year)
                self.engine.mark_abandoned(symbol, "fencing_token_stale")
                self._log({"stage": "fencing_block", "symbol": symbol,
                           "intent_id": intent_id,
                           "owner": self._lease_owner,
                           "token": self._fencing_token})
                self.halt("fencing_token_stale")
                return {"status": "HOLD", "reason": "fencing_token_stale",
                        "symbol": symbol}

        try:
            ticket = self.om.submit_bracket(
                resolved_contract=rc, symbol=symbol, action=action,
                quantity=round(contracts) if contracts >= 1 else round(contracts, 2),
                ref_price=entry, stop_loss=stop, tick_size=tick,
                protect_ticks=3, confirm_live=confirm_live,
                client_ref=intent_id)
        except Exception as exc:
            if self.intent_ledger is not None and intent_id is not None:
                self.intent_ledger.advance_intent(intent_id, "REJECTED")
                row = self.intent_ledger.get_intent(intent_id)
                if row:
                    self.intent_ledger.release_untraded_event(
                        self.account_id, row["event_id"], int(row["event_year"]))
            self.engine.mark_abandoned(symbol, f"submit_exception:{exc}")
            self._log({"stage": "submit_exception", "symbol": symbol,
                       "intent_id": intent_id, "error": str(exc)})
            return {"status": "HOLD", "reason": "submit_exception",
                    "symbol": symbol, "error": str(exc)}

        if self.intent_ledger is not None and intent_id is not None:
            if ticket.state == "SUBMITTED":
                self.intent_ledger.advance_intent(
                    intent_id, "SUBMITTED",
                    broker_order_id=(str(ticket.parent_id)
                                     if ticket.parent_id is not None else None))
            elif ticket.state in ("REJECTED", "CANCELLED"):
                self.intent_ledger.advance_intent(intent_id, ticket.state)
                row = self.intent_ledger.get_intent(intent_id)
                if row:
                    self.intent_ledger.release_untraded_event(
                        self.account_id, row["event_id"], int(row["event_year"]))

        if ticket.state in ("SUBMITTED", "DRYRUN"):
            self.kpi.orders_ready_for_ibkr += 1
            # 登记开仓到学习库（含入场距事件分钟，供冷静期校准）
            if self.journal is not None:
                st = self.engine.states.get(symbol)
                mins = max(0.0, (now - st.event_time).total_seconds() / 60.0) if st else 0.0
                self.journal.record_open(TradeRecord(
                    client_ref=ticket.client_ref, symbol=symbol,
                    event_name=signal.get("event", ""),
                    direction="LONG" if action == "BUY" else "SHORT",
                    entry_price=entry, stop_loss=stop, quantity=ticket.quantity,
                    risk_per_unit=abs(entry - stop), minutes_after_event=mins,
                    multiplier=multiplier,
                    fee_per_side=self.contract_fees.get(symbol, 0.0),
                    model_decision=signal["status"],
                    signal_time=now.isoformat() if hasattr(now, "isoformat") else str(now),
                    submit_time=datetime.now(timezone.utc).isoformat(),
                    signal_price=entry))
        result = {"status": signal["status"], "symbol": symbol,
                  "action": action, "quantity": ticket.quantity,
                  "limit_price": ticket.limit_price, "stop_loss": stop,
                  "order_state": ticket.state, "client_ref": ticket.client_ref,
                  "sizing": sizing_detail, "note": ticket.note}
        self._log({"stage": "order_intent", **result})
        return result

    # ── 成交确认（调用方在拿到券商回报后驱动事件状态推进）─────────────────
    def confirm_fill(self, symbol: str, client_ref: str) -> str:
        ticket = self.om.poll_fill(client_ref)
        intent_row = (self.intent_ledger.get_intent(client_ref)
                      if self.intent_ledger is not None else None)
        if intent_row is not None and ticket.state in ("SUBMITTED", "PARTIAL", "FILLED"):
            self.intent_ledger.advance_intent(
                client_ref, ticket.state,
                broker_order_id=(str(ticket.parent_id)
                                 if ticket.parent_id is not None else None),
                filled_quantity=ticket.filled_quantity)
            if ticket.filled_quantity > 0:
                self.intent_ledger.mark_event_traded(
                    self.account_id, intent_row["event_id"],
                    int(intent_row["event_year"]))
        if (ticket.state in ("PARTIAL", "FILLED")
                and ticket.filled_quantity > 0
                and ticket.average_fill_price > 0
                and ticket.first_fill_time is not None):
            rule = DEFAULT_RULES.get(symbol)
            if rule is not None:
                self.lifecycle.upsert_broker_fill(
                    client_ref, symbol, rule.asset_class,
                    "LONG" if ticket.action == "BUY" else "SHORT",
                    ticket.filled_quantity, ticket.average_fill_price,
                    ticket.first_fill_time)
        if ticket.state == "FILLED":
            trade_row = self.journal.get_trade(client_ref) if self.journal is not None else None
            if self.journal is not None and ticket.fills:
                avg_fill = float(ticket.fills[-1].get("avg") or 0.0)
                if avg_fill > 0:
                    result = self.journal.record_fill(
                        client_ref,
                        fill_price=avg_fill,
                        order_status="FILLED",
                    )
                    if result:
                        self._log({"stage": "trade_filled", "symbol": symbol, **result})
                        direction = trade_row.get("direction", "") if trade_row else ""
                        self.trade_notifier.notify_trade_open(
                            symbol=symbol,
                            direction=direction,
                            fill_price=avg_fill,
                            quantity=ticket.quantity,
                        )
            self.engine.mark_filled(symbol)       # 成交后才关闭事件
        elif ticket.state in ("REJECTED", "CANCELLED"):
            if intent_row is not None:
                self.intent_ledger.advance_intent(client_ref, ticket.state)
                if float(intent_row.get("filled_quantity") or 0.0) <= 0:
                    self.intent_ledger.release_untraded_event(
                        self.account_id, intent_row["event_id"],
                        int(intent_row["event_year"]))
            self.engine.mark_abandoned(symbol, ticket.state)
            self.om.release(symbol)
        return ticket.state

    # ── 平仓：回写真实 P&L 到学习库（替换 pnl_pct=0.0 占位）──────────────
    def on_close(self, symbol: str, client_ref: str, exit_price: float,
                 exit_reason: str = "") -> Optional[Dict[str, Any]]:
        result = None
        trade_before_close = self.journal.get_trade(client_ref) if self.journal is not None else None
        if self.journal is not None:
            result = self.journal.record_close(client_ref, exit_price, exit_reason)
            if result:
                self._log({"stage": "trade_closed", "symbol": symbol, **result})
                trade_after_close = self.journal.get_trade(client_ref)
                if trade_after_close:
                    self.trade_notifier.notify_trade_close(
                        symbol=trade_after_close.get("symbol", symbol),
                        direction=trade_after_close.get("direction", ""),
                        opened_at=trade_after_close.get("opened_at") or (trade_before_close or {}).get("opened_at"),
                        closed_at=trade_after_close.get("closed_at"),
                        entry_price=trade_after_close.get("entry_price"),
                        exit_price=trade_after_close.get("exit_price"),
                        pnl_abs=result.get("pnl_abs"),
                        pnl_pct=result.get("pnl_pct"),
                    )
        if self.intent_ledger is not None:
            self.intent_ledger.advance_intent(client_ref, "CLOSED")
        self.om.release(symbol)
        return result

    def journal_stats(self, symbol: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return self.journal.stats(symbol) if self.journal is not None else None

    def lifecycle_decisions(self, now=None) -> Dict[str, Dict[str, Any]]:
        """Evaluate all broker-confirmed positions against non-negotiable caps."""
        out: Dict[str, Dict[str, Any]] = {}
        for client_ref in list(self.lifecycle.positions):
            decision = self.lifecycle.evaluate(client_ref, now=now)
            out[client_ref] = {
                "action": decision.action,
                "reason": decision.reason,
                "elapsed_seconds": decision.elapsed_seconds,
                "remaining_quantity": decision.remaining_quantity,
            }
        return out

    # ── KPI 计数 ──────────────────────────────────────────────────────────
    def _tally(self, signal: Dict[str, Any]) -> None:
        reason = signal.get("reason", "")
        if reason == "hard_cooldown_active":
            self.kpi.cooldown_active += 1
        if "atr_decayed_to" in str(signal.get("atr_reason", "")) or "atr_decayed_to" in reason:
            self.kpi.atr_whipsaw_finished += 1
        if signal.get("status") in ("BUY", "SELL"):
            self.kpi.body_breakout_passed += 1
            self.kpi.shadow_filter_passed += 1
            if "volume_ok" in str(signal.get("volume_reason", "")) or \
               "volume_not_available" in str(signal.get("volume_reason", "")):
                self.kpi.volume_filter_passed += 1
            if "market_ok" in str(signal.get("market_reason", "")):
                self.kpi.spread_filter_passed += 1
                self.kpi.slippage_filter_passed += 1

    def kpi_report(self) -> Dict[str, Any]:
        rep = {"Right-Side Confirmation Status": self.kpi.as_dict(),
               "shared_risk_wired": self.shared_ok,
               "dry_run": self.dry_run}
        self._log({"stage": "kpi_report", **rep})
        return rep


def _asset_class_for(label: str) -> str:
    """把右侧引擎的 asset_class 映射到 shared ASSET_CONFIGS 的键。"""
    m = {"FX": "FX", "INDEX": "EQUITY_INDEX", "TREASURY": "BOND",
         "RATES": "BOND", "CRYPTO_FUT": "CRYPTO", "CRYPTO_SPOT": "CRYPTO",
         "COMMODITY": "COMMODITY"}
    return m.get(label, "CRYPTO")
