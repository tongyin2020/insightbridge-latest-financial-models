"""
test_crypto_spot.py — 离线自检：BTC 现货(PAXOS) 接入 + 软止损 + 品种启用。
运行：python3 execution_framework/test_crypto_spot.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from enabled_symbols import filter_enabled, ENABLED_SYMBOLS
from ibkr_contract_resolver import CRYPTO_SPECS, ResolvedContract
from ibkr_order_manager import IBKROrderManager
from event_right_side_engine import DEFAULT_RULES


def test_enabled():
    assert "BTC" in ENABLED_SYMBOLS, ENABLED_SYMBOLS
    out = filter_enabled(["MES", "BTC", "MBT"])
    assert "BTC" in out and "MBT" not in out, out
    print("✓ BTC 已启用；MBT(期货) 仍禁用:", out)


def test_rule_and_spec():
    assert "BTC" in DEFAULT_RULES, "缺 BTC AssetRule"
    r = DEFAULT_RULES["BTC"]
    assert r.asset_class == "CRYPTO_SPOT", r.asset_class
    assert "BTC" in CRYPTO_SPECS and CRYPTO_SPECS["BTC"]["exchange"] == "PAXOS"
    print(f"✓ BTC 规则: class={r.asset_class} tick={r.tick_size} "
          f"冷静期={r.min_cooldown_minutes}min；现货交易所={CRYPTO_SPECS['BTC']['exchange']}")


def test_soft_stop_flow():
    om = IBKROrderManager(ib=None, dry_run=True)
    # 模拟一个已锁定的 BTC 现货合约
    rc = ResolvedContract(symbol="BTC", sec_type="CRYPTO", con_id=12345,
                          exchange="PAXOS", currency="USD",
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


def main() -> int:
    test_enabled()
    test_rule_and_spec()
    test_soft_stop_flow()
    print("\n✅ BTC 现货 + 软止损 自检通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
