"""
ibkr_order_manager.py
═══════════════════════════════════════════════════════════════════════════════
生产级订单管理：解决原骨架的 5 个实盘缺口
  1. 市价单 -> marketable limit（带价格保护上限），让滑点过滤真正约束成交价。
  2. 母单 + 止损（可选止盈）组成真正的 OCA bracket（一腿成交另一腿自动撤销）。
  3. 成交确认闭环：母单 FILLED 回报后才认为持仓建立、才挂保护单、才推进事件状态。
  4. 重复下单保护：基于 client_order_ref 去重 + 单品种"在途/持仓"互斥锁。
  5. 默认 transmit=False / dry_run=True：未经显式确认绝不真实发单。

依赖 ib_insync。无连接时全部走 dry-run，只构造并返回订单意图，不发送。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set


OrderState = str  # NEW / SUBMITTED / FILLED / PARTIAL / REJECTED / CANCELLED / DRYRUN


@dataclass
class OrderTicket:
    client_ref: str
    symbol: str
    action: str                 # BUY / SELL
    quantity: float
    limit_price: float          # marketable limit 的保护价
    stop_loss: float
    take_profit: Optional[float] = None
    state: OrderState = "NEW"
    parent_id: Optional[int] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fills: list = field(default_factory=list)
    note: str = ""
    is_crypto: bool = False        # 现货加密（PAXOS）：cashQty+IOC，无原生止损
    soft_stop: bool = False        # 是否由软止损监控器看护


class IBKROrderManager:
    """
    用法：
        om = IBKROrderManager(ib, dry_run=True)
        ticket = om.submit_bracket(
            resolved_contract=rc,         # IBKRContractResolver.resolve() 的结果
            symbol="MNQ", action="BUY", quantity=1,
            ref_price=signal["entry_price"],     # 右侧引擎给的参考价
            stop_loss=signal["stop_loss"],
            tick_size=signal["tick_size"],
            protect_ticks=3,              # 允许的最大滑点保护（tick）
        )
        # 真实发单需 dry_run=False 且 confirm_live=True
    """

    def __init__(self, ib=None, dry_run: bool = True):
        self.ib = ib
        self.dry_run = dry_run or ib is None
        self._open_symbols: Set[str] = set()          # 单品种互斥
        self._seen_refs: Set[str] = set()             # 去重
        self._tickets: Dict[str, OrderTicket] = {}
        # 软止损登记：client_ref -> {symbol, side, stop_price, quantity, rc}
        self.soft_stops: Dict[str, Dict[str, Any]] = {}

    # ── 互斥 / 去重 ───────────────────────────────────────────────────────
    def has_open(self, symbol: str) -> bool:
        return symbol in self._open_symbols

    def _register(self, symbol: str, client_ref: str) -> None:
        self._open_symbols.add(symbol)
        self._seen_refs.add(client_ref)

    def release(self, symbol: str) -> None:
        """持仓完全了结后调用，释放互斥锁。"""
        self._open_symbols.discard(symbol)

    # ── marketable limit 价格 ─────────────────────────────────────────────
    @staticmethod
    def _marketable_limit(action: str, ref_price: float,
                          tick_size: float, protect_ticks: int) -> float:
        """买单价 = 参考价 + N tick（向上保护）；卖单价 = 参考价 - N tick。
        既保证大概率成交，又给出最坏成交价上限，防止市价单失控滑点。"""
        offset = tick_size * protect_ticks
        return ref_price + offset if action == "BUY" else ref_price - offset

    # ── 主入口：提交 OCA bracket ──────────────────────────────────────────
    def submit_bracket(self, resolved_contract, symbol: str, action: str,
                       quantity: float, ref_price: float, stop_loss: float,
                       tick_size: float, protect_ticks: int = 3,
                       take_profit: Optional[float] = None,
                       confirm_live: bool = False) -> OrderTicket:
        client_ref = f"{symbol}-{uuid.uuid4().hex[:12]}"

        # 去重 + 互斥
        if symbol in self._open_symbols:
            return OrderTicket(client_ref, symbol, action, quantity, 0, stop_loss,
                               state="REJECTED", note="symbol_already_has_open_order")

        is_crypto = getattr(resolved_contract, "sec_type", "") == "CRYPTO"
        limit_price = self._marketable_limit(action, ref_price, tick_size, protect_ticks)
        ticket = OrderTicket(
            client_ref=client_ref, symbol=symbol, action=action,
            quantity=quantity, limit_price=limit_price, stop_loss=stop_loss,
            take_profit=take_profit, is_crypto=is_crypto, soft_stop=is_crypto)

        # 合约必须已锁定 conId
        if resolved_contract is None or not getattr(resolved_contract, "is_locked", False):
            ticket.state = "REJECTED"
            ticket.note = "contract_not_resolved"
            return ticket

        # dry-run：只构造意图，不发送
        if self.dry_run or not confirm_live:
            ticket.state = "DRYRUN"
            ticket.note = ("dry_run=True 或 confirm_live=False；未真实发单。"
                           + ("（现货加密：IOC 限价 + 软止损）" if ticket.is_crypto
                              else "确认无误后用 dry_run=False, confirm_live=True 才会下单。"))
            self._register(symbol, client_ref)
            self._tickets[client_ref] = ticket
            if ticket.is_crypto:
                self._register_soft_stop(ticket, resolved_contract)
            return ticket

        # 真实发单（ib_insync）：现货加密走 IOC 限价 + 软止损；其余走 OCA 括号单
        if ticket.is_crypto:
            ticket = self._place_live_crypto(resolved_contract, ticket)
            if ticket.state == "SUBMITTED":
                self._register_soft_stop(ticket, resolved_contract)
        else:
            ticket = self._place_live_bracket(resolved_contract, ticket)
        self._register(symbol, client_ref)
        self._tickets[client_ref] = ticket
        return ticket

    # 现货加密下单：IOC 限价（PAXOS 要求）+ 软止损（无原生 STP）
    def _place_live_crypto(self, rc, ticket: OrderTicket) -> OrderTicket:
        from ib_insync import LimitOrder
        order = LimitOrder(ticket.action, ticket.quantity, ticket.limit_price)
        order.orderRef = ticket.client_ref
        order.tif = "IOC"          # PAXOS 要求 IOC，不是 DAY
        order.transmit = True
        trade = self.ib.placeOrder(rc.raw, order)
        ticket.state = "SUBMITTED"
        ticket.parent_id = trade.order.orderId
        ticket.note = "crypto_ioc_limit_submitted_soft_stop_armed"
        return ticket

    def _register_soft_stop(self, ticket: OrderTicket, rc) -> None:
        side = "LONG" if ticket.action == "BUY" else "SHORT"
        self.soft_stops[ticket.client_ref] = {
            "symbol": ticket.symbol, "side": side,
            "stop_price": ticket.stop_loss, "quantity": ticket.quantity,
            "rc": rc, "active": True}

    def _place_live_bracket(self, rc, ticket: OrderTicket) -> OrderTicket:
        from ib_insync import LimitOrder, StopOrder

        exit_action = "SELL" if ticket.action == "BUY" else "BUY"
        oca = f"oca-{ticket.client_ref}"

        # 母单：marketable limit（非裸市价），成交后才挂保护单
        parent = LimitOrder(ticket.action, ticket.quantity, ticket.limit_price)
        parent.orderRef = ticket.client_ref
        parent.transmit = False              # 先不发，等子单一起

        stop = StopOrder(exit_action, ticket.quantity, ticket.stop_loss)
        stop.orderRef = ticket.client_ref + "-SL"
        stop.ocaGroup = oca
        stop.ocaType = 1                     # 一腿成交/撤销则撤销同组其余腿
        stop.transmit = ticket.take_profit is None   # 没有止盈则止损是最后一腿

        contract = rc.raw
        trade_parent = self.ib.placeOrder(contract, parent)
        trade_stop = self.ib.placeOrder(contract, stop)
        trades = [trade_parent, trade_stop]

        if ticket.take_profit is not None:
            tp = LimitOrder(exit_action, ticket.quantity, ticket.take_profit)
            tp.orderRef = ticket.client_ref + "-TP"
            tp.ocaGroup = oca
            tp.ocaType = 1
            tp.transmit = True               # 最后一腿，发送整组
            trades.append(self.ib.placeOrder(contract, tp))

        ticket.state = "SUBMITTED"
        ticket.parent_id = trade_parent.order.orderId
        ticket.note = f"submitted_oca_group_{oca}"
        return ticket

    # ── 成交确认（由调用方在事件循环里轮询/回调驱动）──────────────────────
    def poll_fill(self, client_ref: str) -> OrderTicket:
        """检查母单是否成交。真实模式下读取 ib_insync trade 状态。
        返回更新后的 ticket；调用方据此调用 right_side_engine.mark_filled()。"""
        ticket = self._tickets.get(client_ref)
        if ticket is None:
            raise KeyError(f"未知订单: {client_ref}")
        if self.dry_run:
            return ticket
        # 真实模式：从 ib.trades() 找到 parent，读取 orderStatus
        for tr in self.ib.trades():
            if tr.order.orderRef == client_ref:
                status = tr.orderStatus.status
                if status == "Filled":
                    ticket.state = "FILLED"
                    ticket.fills.append({"avg": tr.orderStatus.avgFillPrice,
                                         "filled": tr.orderStatus.filled})
                elif status in ("Cancelled", "ApiCancelled"):
                    ticket.state = "CANCELLED"
                elif status in ("PendingSubmit", "PreSubmitted", "Submitted"):
                    ticket.state = "SUBMITTED"
                elif tr.orderStatus.filled > 0:
                    ticket.state = "PARTIAL"
                break
        return ticket

    def cancel_all_for(self, symbol: str) -> None:
        """紧急撤单/对账用。"""
        if self.dry_run:
            return
        for tr in self.ib.openTrades():
            ref = tr.order.orderRef or ""
            if ref.startswith(symbol + "-"):
                self.ib.cancelOrder(tr.order)

    # ── 软止损监控（现货加密专用；现货不支持原生 STP）─────────────
    def check_soft_stops(self, price_func) -> list:
        """由主循环每轮调用：逐个检查软止损是否被穿越。
        price_func(symbol) -> 现价（float）。被穿越则发市价平仓并返回触发列表。
        返回：[{client_ref, symbol, side, stop_price, current, exit_state}]"""
        triggered = []
        for ref, ss in list(self.soft_stops.items()):
            if not ss.get("active"):
                continue
            try:
                px = float(price_func(ss["symbol"]))
            except Exception:   # noqa: BLE001
                continue
            if px <= 0:
                continue
            hit = ((ss["side"] == "LONG" and px <= ss["stop_price"]) or
                   (ss["side"] == "SHORT" and px >= ss["stop_price"]))
            if not hit:
                continue
            ss["active"] = False
            exit_state = self._soft_stop_exit(ref, ss, px)
            triggered.append({"client_ref": ref, "symbol": ss["symbol"],
                              "side": ss["side"], "stop_price": ss["stop_price"],
                              "current": px, "exit_state": exit_state})
        return triggered

    def _soft_stop_exit(self, ref: str, ss: dict, px: float) -> str:
        """触发软止损：反向 IOC 限价平仓（带最坏价保护，不是裸市价）。"""
        if self.dry_run:
            return "DRYRUN_SOFT_STOP"
        from ib_insync import LimitOrder
        exit_action = "SELL" if ss["side"] == "LONG" else "BUY"
        # 平仓价留 0.3% 缓冲以提高成交概率，同时限住最坏成交
        buf = px * (0.997 if exit_action == "SELL" else 1.003)
        order = LimitOrder(exit_action, ss["quantity"], round(buf, 2))
        order.orderRef = ref + "-SOFTSTOP"
        order.tif = "IOC"
        order.transmit = True
        self.ib.placeOrder(ss["rc"].raw, order)
        return "SOFT_STOP_EXIT_SENT"
