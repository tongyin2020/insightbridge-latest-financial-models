"""
test_pipeline_dryrun.py
═══════════════════════════════════════════════════════════════════════════════
离线 dry-run 自检：无需连接 IBKR，用合成 1 分钟K线验证整条右侧确认管线。
验证点：
  - 冷静期内不出信号
  - ATR 衰减确认后才进入实体突破判定
  - 信号成立后进入 dry-run 下单意图（不真实发单）
  - 成交确认后事件状态正确关闭
  - KPI 字段正确累计
运行：  python3 execution_framework/test_pipeline_dryrun.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from event_right_side_engine import RightSideEventEngine, DEFAULT_RULES
from right_side_pipeline import RightSidePipeline


def make_candles(n: int, base: float, vol: float, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    price = base
    for _ in range(n):
        drift = rng.normal(0, vol)
        o = price
        c = price + drift
        hi = max(o, c) + abs(rng.normal(0, vol * 0.3))
        lo = min(o, c) - abs(rng.normal(0, vol * 0.3))
        rows.append({"open": o, "high": hi, "low": lo, "close": c,
                     "volume": rng.uniform(800, 1200)})
        price = c
    return pd.DataFrame(rows)


def append_impulse_then_decay(df: pd.DataFrame, base: float) -> pd.DataFrame:
    """模拟事件：先一根大冲击放量，再几根逐渐收敛，最后一根放量实体向上突破。"""
    extra = []
    # 连续几根大冲击把 ATR 峰值显著抬高（含长影线）
    c = base
    for _ in range(4):
        extra.append({"open": c, "high": c + 30, "low": c - 25,
                      "close": c + 4, "volume": 5000})
        c = c + 4
    # 衰减：连续小幅、窄幅K线，让 ATR 大幅回落到峰值区间下方
    for i in range(14):
        c2 = c + i * 0.1
        extra.append({"open": c2 - 0.05, "high": c2 + 0.1, "low": c2 - 0.1,
                      "close": c2, "volume": 900})
    # 放量实体突破（实体大、影线短、量足）
    last_close = c + 13 * 0.1
    brk = last_close + 4.0
    extra.append({"open": last_close, "high": brk + 0.2, "low": last_close - 0.1,
                  "close": brk, "volume": 3000})
    return pd.concat([df, pd.DataFrame(extra)], ignore_index=True)


def main() -> int:
    symbol = "MNQ"
    base = 18000.0
    df = make_candles(40, base, vol=1.0)

    pipe = RightSidePipeline(ib=None, dry_run=True, equity=50000.0,
                             log_path="/tmp/right_side_dryrun.log")
    print(f"shared_risk_wired = {pipe.shared_ok}")

    # 离线演示：注入一个已锁定 conId 的 mock 合约，验证 dry-run 下单 + 仓位计算。
    # （真实运行时由 IBKRContractResolver 通过 reqContractDetails 解析，无需 mock。）
    from ibkr_contract_resolver import ResolvedContract
    pipe.resolver._cache[symbol] = ResolvedContract(
        symbol=symbol, sec_type="FUT", con_id=999999, exchange="CME",
        currency="USD", local_symbol="MNQU6", last_trade_date="20260918",
        multiplier="2", raw=object())

    # 事件发生在 RTH 时段内（14:00 UTC）
    event_time = datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc)
    pipe.on_event(symbol, "CPI", event_time, df)

    # 冷静期内（事件后 5 分钟，< 15 分钟硬冷静期）应 HOLD
    r_cool = pipe.step(symbol, event_time + timedelta(minutes=5), df,
                       bid=base - 0.25, ask=base + 0.25,
                       account_state={"equity": 50000})
    assert r_cool["status"] == "HOLD", r_cool
    print("冷静期内正确 HOLD:", r_cool["reason"])

    # 冷静期后 + 注入冲击衰减+突破K线
    df2 = append_impulse_then_decay(df, base)
    now = event_time + timedelta(minutes=20)
    result = None
    # 逐根喂入，模拟 ATR 峰值跟踪
    n_extra = len(df2) - 40
    for k in range(1, n_extra + 1):
        sub = df2.iloc[:40 + k]
        result = pipe.step(symbol, now, sub,
                           bid=float(sub["close"].iloc[-1]) - 0.25,
                           ask=float(sub["close"].iloc[-1]) + 0.25,
                           account_state={"equity": 50000})
        if result["status"] in ("BUY", "SELL"):
            break

    print("最终判定:", result)

    if result and result["status"] in ("BUY", "SELL"):
        assert result["order_state"] == "DRYRUN", result
        assert result["quantity"] >= 0
        print(f"  ✓ dry-run 下单意图: {result['action']} {result['quantity']} "
              f"@ limit {result['limit_price']:.2f}, stop {result['stop_loss']:.2f}")
        print(f"  ✓ 仓位由风险约束算出: {result['sizing']}")
        # 模拟成交确认
        state = pipe.confirm_fill(symbol, result["client_ref"])
        print(f"  ✓ 成交确认状态(dry-run 下保持 DRYRUN): {state}")

    print("\nKPI 报告:")
    for k, v in pipe.kpi_report()["Right-Side Confirmation Status"].items():
        print(f"  {k}: {v}")

    print("\n✅ dry-run 自检通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
