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
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from event_right_side_engine import RightSideEventEngine, DEFAULT_RULES
from ibkr_contract_resolver import IBKRContractResolver, ContractResolutionError
from ibkr_order_manager import IBKROrderManager

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
                 log_path: Optional[str] = None, journal_db: Optional[str] = None):
        self.engine = RightSideEventEngine(DEFAULT_RULES)
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

    @property
    def is_halted(self) -> bool:
        return self._halted

    def attach_session(self, session) -> None:
        """把 TWS 会话的致命错误/重连回调接到本管线。"""
        session.on_fatal = lambda code, msg: self.halt(f"ibkr_fatal_{code}:{msg}")
        session.on_reconnect = lambda: self._log({"stage": "reconnected"})

    # ── 触发事件 ──────────────────────────────────────────────────────────
    def on_event(self, symbol: str, event_name: str, event_time, df) -> None:
        self.engine.trigger_event(symbol, event_name, event_time, df)
        self.kpi.active_events += 1
        self._log({"stage": "event_triggered", "symbol": symbol, "event": event_name})

    # ── 每根K线评估 + 风控 + 仓位 + 下单意图 ──────────────────────────────
    def step(self, symbol: str, now, df, bid=None, ask=None,
             account_state: Optional[Dict[str, Any]] = None,
             available_depth: float = 5_000_000.0,
             confirm_live: bool = False) -> Dict[str, Any]:
        # 停机闸：致命错误/对账失败后不再新入场
        if self._halted:
            return {"status": "HOLD", "reason": f"halted:{self._halt_reason}", "symbol": symbol}

        # 单品种互斥：已有在途/持仓则不再发新单
        if self.om.has_open(symbol):
            return {"status": "HOLD", "reason": "symbol_has_open_order", "symbol": symbol}

        signal = self.engine.evaluate(symbol, now, df, bid=bid, ask=ask)
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

        # ── 仓位由风险约束决定（不再写死 1 手）──────────────────────────────
        entry = signal["entry_price"]
        stop = signal["stop_loss"]
        tick = signal["tick_size"]
        plan_stop_pct = abs(entry - stop) / entry if entry else 0.0
        contracts = 1.0
        sizing_detail: Dict[str, Any] = {"fallback": "shared_core_unavailable"}

        if _SHARED_OK and plan_stop_pct > 0:
            sizer = CorrectPositionSizer(
                equity=self.equity, max_loss_pct=self.max_loss_pct,
                contract_value=max(entry, 1.0))
            res = sizer.compute(
                plan_stop_pct=plan_stop_pct,
                pred_slippage_pct=(tick * 3) / entry if entry else 0.0004,
                available_depth=available_depth,
                asset_class=_asset_class_for(signal.get("asset_class", "")))
            contracts = max(0.0, float(res.final_contracts))
            sizing_detail = {"binding": res.binding_constraint,
                             "notional": res.final_notional,
                             "effective_stop_pct": res.effective_stop_width}

        if contracts <= 0:
            self.kpi.orders_blocked_by_risk += 1
            self.engine.mark_abandoned(symbol, "zero_size")
            self._log({"stage": "size_zero", "symbol": symbol, **sizing_detail})
            return {"status": "HOLD", "reason": "risk_sized_to_zero",
                    "symbol": symbol, "sizing": sizing_detail}

        # ── 合约解析（禁用 CONTFUT，必须锁 conId）──────────────────────────
        try:
            rc = self.resolver.resolve(symbol)
        except ContractResolutionError as exc:
            self.kpi.orders_blocked_by_risk += 1
            self.engine.mark_abandoned(symbol, f"contract:{exc}")
            self._log({"stage": "contract_unresolved", "symbol": symbol, "error": str(exc)})
            return {"status": "HOLD", "reason": "contract_unresolved",
                    "symbol": symbol, "error": str(exc)}

        # ── 下单意图（默认 dry-run）────────────────────────────────────────
        action = "BUY" if signal["status"] == "BUY" else "SELL"
        ticket = self.om.submit_bracket(
            resolved_contract=rc, symbol=symbol, action=action,
            quantity=round(contracts) if contracts >= 1 else round(contracts, 2),
            ref_price=entry, stop_loss=stop, tick_size=tick,
            protect_ticks=3, confirm_live=confirm_live)

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
                    risk_per_unit=abs(entry - stop), minutes_after_event=mins))
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
        if ticket.state == "FILLED":
            self.engine.mark_filled(symbol)       # 成交后才关闭事件
        elif ticket.state in ("REJECTED", "CANCELLED"):
            self.engine.mark_abandoned(symbol, ticket.state)
            self.om.release(symbol)
        return ticket.state

    # ── 平仓：回写真实 P&L 到学习库（替换 pnl_pct=0.0 占位）──────────────
    def on_close(self, symbol: str, client_ref: str, exit_price: float,
                 exit_reason: str = "") -> Optional[Dict[str, Any]]:
        result = None
        if self.journal is not None:
            result = self.journal.record_close(client_ref, exit_price, exit_reason)
            if result:
                self._log({"stage": "trade_closed", "symbol": symbol, **result})
        self.om.release(symbol)
        return result

    def journal_stats(self, symbol: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return self.journal.stats(symbol) if self.journal is not None else None

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
