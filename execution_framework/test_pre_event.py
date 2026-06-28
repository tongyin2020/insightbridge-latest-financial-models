"""
test_pre_event.py — 离线自检：会前降温（冻结新入场 + 平现货持仓）+ 8月日历。
运行：python3 execution_framework/test_pre_event.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from economic_calendar import EconomicCalendar
from ibkr_contract_resolver import ResolvedContract
from right_side_pipeline import RightSidePipeline


def _df(n=50, base=18000.0):
    rng = np.random.default_rng(5)
    rows, p = [], base
    for _ in range(n):
        c = p + rng.normal(0, 1)
        rows.append({"open": p, "high": max(p, c) + 0.5, "low": min(p, c) - 0.5,
                     "close": c, "volume": rng.uniform(800, 1200)})
        p = c
    return pd.DataFrame(rows)


def test_imminent():
    cal = EconomicCalendar(enabled_symbols=["MES", "MNQ", "BTC"])
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    cal.add("CPI", now + timedelta(minutes=10), title="CPI")   # 10 分钟后
    cal.add("CPI", now + timedelta(minutes=40), title="later")  # 40 分钟后
    imm = cal.imminent(now, lead_minutes=15)
    assert len(imm) == 1, imm   # 只有 10 分钟后的进入会前窗口
    print("✓ imminent(15min) 正确识别 10 分钟后的事件，不含 40 分钟后的")


def test_pre_event_freeze_and_flatten():
    pipe = RightSidePipeline(ib=None, dry_run=True, equity=50000.0)
    # 注入 MNQ 期货 + BTC 现货已锁定合约
    pipe.resolver._cache["MNQ"] = ResolvedContract("MNQ", "FUT", 111, "CME", "USD",
                                                   local_symbol="MNQU6", raw=object())
    pipe.resolver._cache["BTC"] = ResolvedContract("BTC", "CRYPTO", 222, "PAXOS", "USD",
                                                   local_symbol="BTC.USD", raw=object())
    # 先给 BTC 建一个软止损持仓（dry-run）
    t = pipe.om.submit_bracket(pipe.resolver._cache["BTC"], "BTC", "BUY", 0.01,
                               ref_price=60000, stop_loss=59000, tick_size=0.01)
    assert t.client_ref in pipe.om.soft_stops and pipe.om.soft_stops[t.client_ref]["active"]

    # 会前降温：冻结 MNQ+BTC，并平掉 BTC 软止损持仓
    rec = pipe.pre_event_cooldown(["MNQ", "BTC"], "CPI",
                                  price_func=lambda s: 60500.0, flatten=True)
    assert set(rec["frozen"]) == {"MNQ", "BTC"}, rec
    assert len(rec["crypto_flattened"]) == 1, rec
    assert not pipe.om.soft_stops[t.client_ref]["active"], "BTC 软止损持仓未被会前平掉"
    print(f"✓ 会前降温：冻结 {rec['frozen']}，平掉 BTC 现货持仓 {len(rec['crypto_flattened'])} 笔")

    # 冻结期间新入场被拦
    r = pipe.step("MNQ", datetime.now(timezone.utc), _df())
    assert r["reason"] == "pre_event_frozen", r
    print("✓ 冻结期间 MNQ 新入场被拦:", r["reason"])

    # 事件触发后解除冻结
    pipe.clear_pre_event_freeze(["MNQ", "BTC"])
    r2 = pipe.step("MNQ", datetime.now(timezone.utc), _df())
    assert r2["reason"] != "pre_event_frozen", r2
    print("✓ 事件触发后解除冻结，恢复正常评估:", r2["reason"])


def test_aug_calendar():
    # 验证 8 月官方日期已可被加载（用 EVENT_IMPACT 映射）
    cal = EconomicCalendar(enabled_symbols=["MES", "MNQ", "ZT", "ZN", "SR3",
                                            "EURUSD", "USDJPY", "BTC"])
    cal.add("CPI", datetime(2026, 8, 12, 12, 30, tzinfo=timezone.utc), title="CPI Jul")
    cal.add("NFP", datetime(2026, 8, 7, 12, 30, tzinfo=timezone.utc), title="NFP Jul")
    cpi = [e for e in cal.events if e.name == "CPI"][0]
    nfp = [e for e in cal.events if e.name == "NFP"][0]
    assert "BTC" in cpi.symbols and "BTC" not in nfp.symbols
    print(f"✓ 8月日历: CPI含BTC={('BTC' in cpi.symbols)}, NFP含BTC={('BTC' in nfp.symbols)}")


def main() -> int:
    test_imminent()
    test_pre_event_freeze_and_flatten()
    test_aug_calendar()
    print("\n✅ 会前降温 + 8月日历 自检通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
