"""Offline regression tests for the 2026-08-27 review fixes in
ibkr_order_manager.py:

  A. poll_fill matches the parent order by orderId even when orderRef is
     unavailable (IBKR documents orderRef as institutional-only) and even when
     client_ref is a 32-char ledger hash that carries no symbol prefix.
  B. cancel_all_for cancels a symbol's orders from the process-tracked trade
     registry (orderId/permId), not from an orderRef "SYMBOL-" prefix — the old
     implementation silently cancelled nothing once the intent ledger supplied
     hash client_refs.
  C. Soft-stop exit prices are rounded to the contract tick_size, not to a
     hard-coded 2 decimals (SOL tick=0.001 produced illegal prices).

Runs without TWS: a minimal fake ib_insync surface is provided.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


# ── minimal fake ib_insync ──────────────────────────────────────────────────
class _FakeOrderBase:
    def __init__(self, action, quantity, price=None):
        self.action = action
        self.totalQuantity = quantity
        self.lmtPrice = price
        self.auxPrice = price
        self.orderId = 0
        self.permId = 0
        self.orderRef = ""
        self.parentId = 0
        self.ocaGroup = ""
        self.ocaType = 0
        self.tif = "DAY"
        self.transmit = True


def _install_fake_ib_insync():
    module = types.ModuleType("ib_insync")

    class LimitOrder(_FakeOrderBase):
        def __init__(self, action, quantity, limit_price):
            super().__init__(action, quantity, limit_price)

    class StopOrder(_FakeOrderBase):
        def __init__(self, action, quantity, stop_price):
            super().__init__(action, quantity, stop_price)

    module.LimitOrder = LimitOrder
    module.StopOrder = StopOrder
    sys.modules["ib_insync"] = module


_install_fake_ib_insync()

from ibkr_order_manager import IBKROrderManager  # noqa: E402


class FakeStatus:
    def __init__(self, status="Submitted", filled=0.0, avg=0.0):
        self.status = status
        self.filled = filled
        self.avgFillPrice = avg


class FakeTrade:
    _next_perm = 900000

    def __init__(self, order, contract):
        self.order = order
        self.contract = contract
        self.orderStatus = FakeStatus()
        self.fills = []
        FakeTrade._next_perm += 1
        order.permId = FakeTrade._next_perm


class FakeContract:
    def __init__(self, symbol):
        self.symbol = symbol


class FakeResolved:
    def __init__(self, symbol, sec_type="FUT"):
        self.sec_type = sec_type
        self.is_locked = True
        self.raw = FakeContract(symbol)
        self.multiplier = "2"


class FakeIB:
    """Minimal ib_insync IB surface: placeOrder/trades/openTrades/cancelOrder."""

    def __init__(self):
        self._trades = []
        self._next_id = 1000
        self.cancelled = []

    def placeOrder(self, contract, order):
        self._next_id += 1
        order.orderId = self._next_id
        trade = FakeTrade(order, contract)
        self._trades.append(trade)
        return trade

    def trades(self):
        return list(self._trades)

    def openTrades(self):
        return list(self._trades)

    def cancelOrder(self, order):
        self.cancelled.append(order.orderId)
        order._cancelled = True


LEDGER_STYLE_REF = "9f86d081884c7d659a2feaa0c55ad015"   # 32-hex, no symbol prefix


def test_poll_fill_matches_by_orderid_without_orderref():
    ib = FakeIB()
    om = IBKROrderManager(ib=ib, dry_run=False)
    ticket = om.submit_bracket(
        FakeResolved("MNQ"), symbol="MNQ", action="BUY", quantity=1,
        ref_price=18000.0, stop_loss=17990.0, tick_size=0.25,
        confirm_live=True, client_ref=LEDGER_STYLE_REF)
    assert ticket.state == "SUBMITTED"

    # 模拟机构权限缺失：券商侧拿不到 orderRef（对象上被清空/不可见）
    for tr in ib.trades():
        tr.order.orderRef = None

    parent = next(tr for tr in ib.trades()
                  if tr.order.orderId == ticket.parent_id)
    parent.orderStatus.status = "Filled"
    parent.orderStatus.filled = 1.0
    parent.orderStatus.avgFillPrice = 18001.25

    updated = om.poll_fill(LEDGER_STYLE_REF)
    assert updated.state == "FILLED"
    assert updated.filled_quantity == 1.0
    assert abs(updated.average_fill_price - 18001.25) < 1e-9
    print("✓ poll_fill matches parent by orderId without orderRef")


def test_cancel_all_for_uses_tracked_orders_not_ref_prefix():
    ib = FakeIB()
    om = IBKROrderManager(ib=ib, dry_run=False)
    om.submit_bracket(
        FakeResolved("MNQ"), symbol="MNQ", action="BUY", quantity=1,
        ref_price=18000.0, stop_loss=17990.0, tick_size=0.25,
        take_profit=18020.0,
        confirm_live=True, client_ref=LEDGER_STYLE_REF)
    # orderRef 是哈希（不含 "MNQ-" 前缀）——旧实现此时一个也撤不到
    om.cancel_all_for("MNQ")
    placed_ids = {tr.order.orderId for tr in ib.trades()}
    assert placed_ids, "expected orders to have been placed"
    assert placed_ids <= set(ib.cancelled), (
        f"not all tracked orders cancelled: {placed_ids - set(ib.cancelled)}")
    print("✓ cancel_all_for cancels via tracked orderIds (hash client_ref)")


def test_cancel_all_for_fallback_matches_contract_symbol():
    """重连后进程登记丢失：openTrades 扫描按合约品种兜底，不靠 orderRef。"""
    ib = FakeIB()
    om = IBKROrderManager(ib=ib, dry_run=False)
    om.submit_bracket(
        FakeResolved("ZN"), symbol="ZN", action="SELL", quantity=1,
        ref_price=110.0, stop_loss=110.5, tick_size=0.015625,
        confirm_live=True, client_ref=LEDGER_STYLE_REF)
    for tr in ib.trades():
        tr.order.orderRef = None
    om._trades.clear()          # 模拟进程重启：登记丢失
    om.cancel_all_for("ZN")
    placed_ids = {tr.order.orderId for tr in ib.trades()}
    assert placed_ids <= set(ib.cancelled)
    print("✓ cancel_all_for falls back to contract-symbol matching")


def test_soft_stop_exit_rounds_to_contract_tick():
    ib = FakeIB()
    om = IBKROrderManager(ib=ib, dry_run=False)
    # SOL：tick=0.001。旧实现 round(buf, 2) 会产生非法价格颗粒。
    rc = FakeResolved("SOL", sec_type="CRYPTO")
    ticket = om.submit_bracket(
        rc, symbol="SOL", action="BUY", quantity=10,
        ref_price=100.123, stop_loss=98.50, tick_size=0.001,
        confirm_live=True, client_ref=LEDGER_STYLE_REF)
    assert ticket.is_crypto and ticket.soft_stop

    # 实盘加密设计：软止损只按券商确认成交数量武装 -> 先模拟一笔成交
    parent = next(tr for tr in ib.trades()
                  if tr.order.orderId == ticket.parent_id)
    parent.orderStatus.status = "Filled"
    parent.orderStatus.filled = 10.0
    parent.orderStatus.avgFillPrice = 100.10
    om.poll_fill(LEDGER_STYLE_REF)

    ss = om.soft_stops[LEDGER_STYLE_REF]
    assert ss["tick_size"] == 0.001
    assert ss["quantity"] == 10.0

    # 价格跌破止损 -> 触发软止损平仓
    triggered = om.check_soft_stops(lambda symbol: 98.40)
    assert triggered and triggered[0]["exit_state"] == "SOFT_STOP_EXIT_SENT"
    exit_order = ib.trades()[-1].order
    price = exit_order.lmtPrice
    # 必须是 0.001 的整数倍
    assert abs(price / 0.001 - round(price / 0.001)) < 1e-6, price
    # 且保留 0.3% 缓冲后的语义：低于触发价（卖出方向向下保护）
    assert price < 98.40
    print("✓ soft-stop exit price rounds to contract tick_size")


def main() -> int:
    test_poll_fill_matches_by_orderid_without_orderref()
    test_cancel_all_for_uses_tracked_orders_not_ref_prefix()
    test_cancel_all_for_fallback_matches_contract_symbol()
    test_soft_stop_exit_rounds_to_contract_tick()
    print("\n✅ 2026-08-27 review fixes verified (ibkr_order_manager).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
