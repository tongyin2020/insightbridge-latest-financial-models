"""
test_crypto_spot.py — 离线自检：BTC 现货(ZEROHASH) 接入 + 软止损 + 品种启用。
运行：python3 execution_framework/test_crypto_spot.py
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from enabled_symbols import filter_enabled, ENABLED_SYMBOLS
from ibkr_contract_resolver import CRYPTO_SPECS, ResolvedContract
from ibkr_order_manager import IBKROrderManager
from event_right_side_engine import DEFAULT_RULES


class _Status:
    status = "Submitted"
    filled = 0.0
    avgFillPrice = 0.0


class _Trade:
    def __init__(self, order):
        self.order = order
        self.orderStatus = _Status()


class _FakeIB:
    def __init__(self):
        self._trades = []

    def placeOrder(self, _contract, order):
        order.orderId = len(self._trades) + 1
        trade = _Trade(order)
        self._trades.append(trade)
        return trade

    def trades(self):
        return self._trades


class _FakeLimitOrder:
    def __init__(self, action, quantity, limit_price, **kwargs):
        self.action = action
        self.totalQuantity = quantity
        self.lmtPrice = limit_price
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_enabled():
    assert "BTC" in ENABLED_SYMBOLS, ENABLED_SYMBOLS
    out = filter_enabled(["MES", "BTC", "MBT"])
    assert "BTC" in out and "MBT" not in out, out
    print("✓ BTC 已启用；MBT(期货) 仍禁用:", out)


def test_rule_and_spec():
    assert "BTC" in DEFAULT_RULES, "缺 BTC AssetRule"
    r = DEFAULT_RULES["BTC"]
    assert r.asset_class == "CRYPTO_SPOT", r.asset_class
    assert "BTC" in CRYPTO_SPECS and CRYPTO_SPECS["BTC"]["exchange"] == "ZEROHASH"
    print(f"✓ BTC 规则: class={r.asset_class} tick={r.tick_size} "
          f"冷静期={r.min_cooldown_minutes}min；现货交易所={CRYPTO_SPECS['BTC']['exchange']}")


def test_soft_stop_flow():
    om = IBKROrderManager(ib=None, dry_run=True)
    # 模拟一个已锁定的 BTC 现货合约
    rc = ResolvedContract(symbol="BTC", sec_type="CRYPTO", con_id=12345,
                          exchange="ZEROHASH", currency="USD",
                          local_symbol="BTC.USD", raw=object())
    # 多单：入场 60000，止损 59000，数量 0.01 BTC
    ticket = om.submit_bracket(resolved_contract=rc, symbol="BTC", action="BUY",
                               quantity=0.01, ref_price=60000.0, stop_loss=59000.0,
                               tick_size=0.01, protect_ticks=3)
    assert ticket.is_crypto and ticket.soft_stop, ticket
    assert ticket.state == "DRYRUN", ticket
    assert ticket.client_ref in om.soft_stops, "软止损未登记"
    print(f"✓ BTC 现货 dry-run 下单意图: {ticket.action} {ticket.quantity} "
          f"@ limit {ticket.limit_price:.2f}, 软止损 {ticket.stop_loss}")

    # 价格高于止损 -> 不触发
    fired = om.check_soft_stops(lambda s: 59500.0)
    assert fired == [], fired
    print("✓ 价 59500 > 止损 59000：软止损未触发")

    # 价格穿过止损 -> 触发（dry-run 下返回 DRYRUN_SOFT_STOP）
    fired = om.check_soft_stops(lambda s: 58900.0)
    assert len(fired) == 1 and fired[0]["exit_state"] == "DRYRUN_SOFT_STOP", fired
    print(f"✓ 价 58900 <= 止损 59000：软止损触发 -> {fired[0]['exit_state']}")

    # 已触发不重复
    fired2 = om.check_soft_stops(lambda s: 58000.0)
    assert fired2 == [], fired2
    print("✓ 软止损不重复触发")


def test_live_soft_stop_uses_confirmed_fill_quantity():
    fake_ib_insync = types.ModuleType("ib_insync")
    fake_ib_insync.LimitOrder = _FakeLimitOrder
    previous = sys.modules.get("ib_insync")
    sys.modules["ib_insync"] = fake_ib_insync
    ib = _FakeIB()
    try:
        om = IBKROrderManager(ib=ib, dry_run=False)
        rc = ResolvedContract(symbol="BTC", sec_type="CRYPTO", con_id=12345,
                              exchange="ZEROHASH", currency="USD",
                              local_symbol="BTC.USD", raw=object())
        ticket = om.submit_bracket(
            resolved_contract=rc, symbol="BTC", action="BUY", quantity=0.01,
            ref_price=60000.0, stop_loss=59000.0, tick_size=0.01,
            protect_ticks=3, confirm_live=True)
        assert ticket.state == "SUBMITTED"
        assert ticket.client_ref not in om.soft_stops
        ib._trades[0].orderStatus.status = "Filled"
        ib._trades[0].orderStatus.filled = 0.006
        ib._trades[0].orderStatus.avgFillPrice = 60000.0
        ticket = om.poll_fill(ticket.client_ref)
        assert ticket.state == "FILLED"
        assert om.soft_stops[ticket.client_ref]["quantity"] == 0.006
        print("✓ live crypto soft stop is armed only for broker-confirmed quantity")
    finally:
        if previous is None:
            sys.modules.pop("ib_insync", None)
        else:
            sys.modules["ib_insync"] = previous


def main() -> int:
    test_enabled()
    test_rule_and_spec()
    test_soft_stop_flow()
    test_live_soft_stop_uses_confirmed_fill_quantity()
    print("\n✅ BTC 现货 + 软止损 自检通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
