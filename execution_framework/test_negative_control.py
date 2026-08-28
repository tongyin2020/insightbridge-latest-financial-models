"""Negative-control harness tests (R1-2 methodology check).

These tests validate the HARNESS on crafted data where the truth is known:
a continuation tape must produce a positive paired diff, a reversal tape a
negative one, and the permutation test must separate "direction carries
information" from noise.  Whether the real edge exists can only be answered
once shadow archives accumulate -- that is what the harness is for.
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from event_data_archive import EventDataArchive
from event_right_side_engine import AssetRule
from negative_control import (load_event, replay_event, simulate_outcome,
                              permutation_pvalue, verdict, run)

T0 = datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc)
RULE = AssetRule("TEST", "INDEX", 2, 30, tick_size=0.25,
                 max_spread_ticks=3.0, max_slippage_ticks=4.0)
CAP_S = 300  # 测试用 5 分钟硬封顶，压缩磁带长度


def _bar(minutes_after: float, o: float, c: float, h: float, l: float,
         v: float = 100.0, base: datetime = T0) -> dict:
    return {"bar_time": (base + timedelta(minutes=minutes_after)).isoformat(),
            "open": o, "close": c, "high": h, "low": l, "volume": v,
            "bar_size": "1 min"}


def _pre_bars() -> list:
    # 25 根平静 bar（TR=0.2）+ t0 事件冲击 bar（TR=2.7，收 101.5）
    bars = [_bar(-25 + i, 100.0, 100.0, 100.1, 99.9) for i in range(25)]
    bars.append(_bar(0, 100.0, 101.5, 102.5, 99.8, v=500))
    return bars


def _decay_and_breakout() -> list:
    # 14 根衰减 bar（TR≈0.25，缓慢上移）+ 第 15 根实体突破 bar
    bars = []
    for k in range(1, 15):
        mid = 101.2 + 0.02 * k
        bars.append(_bar(k, mid - 0.05, mid + 0.05,
                         mid + 0.125, mid - 0.125))
    # 实体突破：收 102.45 > 前 10 根实体高点 101.53；量 2 倍
    bars.append(_bar(15, 101.5, 102.45, 102.5, 101.4, v=200))
    return bars


def _df(bars: list) -> pd.DataFrame:
    rows = []
    for b in bars:
        rows.append({"date": datetime.fromisoformat(b["bar_time"]),
                     "open": b["open"], "close": b["close"],
                     "high": b["high"], "low": b["low"], "volume": b["volume"]})
    return pd.DataFrame(rows)


def test_engine_fires_on_crafted_tape():
    df = _df(_pre_bars() + _decay_and_breakout())
    rec = replay_event(RULE, "TEST", "CPI", T0, df, cap_seconds=CAP_S)
    assert rec["entered"] == 1, rec
    assert rec["direction"] == "LONG"
    assert abs(rec["entry_price"] - 102.45) < 1e-9
    assert abs(rec["stop_loss"] - 101.4) < 1e-9


def test_continuation_tape_gives_positive_diff():
    tail = [_bar(16 + i, 102.45 + 0.2 * i, 102.65 + 0.2 * i,
                 102.7 + 0.2 * i, 102.4 + 0.2 * i) for i in range(6)]
    df = _df(_pre_bars() + _decay_and_breakout() + tail)
    rec = replay_event(RULE, "TEST", "CPI", T0, df, cap_seconds=CAP_S)
    # 5 分钟后 cap 出场：R_long = (103.65-102.45)/1.05 ≈ +1.14（精确值按 bar 序列）
    assert rec["r_signal"] > 0.9
    assert rec["r_long"] > 0.9 and rec["r_short"] < -0.9
    assert rec["paired_diff"] > 0.9
    assert rec["exit_reason"] == "hard_hold_cap"


def test_reversal_tape_gives_negative_diff():
    tail = [
        _bar(16, 102.4, 101.7, 102.45, 101.6),
        _bar(17, 101.7, 101.2, 101.75, 101.2),   # 触发多头止损 101.4
        _bar(18, 101.2, 101.2, 101.3, 101.1),
        _bar(19, 101.2, 101.2, 101.3, 101.1),
        _bar(20, 101.2, 101.2, 101.3, 101.1),
        _bar(21, 101.2, 101.2, 101.3, 101.1),
    ]
    df = _df(_pre_bars() + _decay_and_breakout() + tail)
    rec = replay_event(RULE, "TEST", "CPI", T0, df, cap_seconds=CAP_S)
    assert rec["r_signal"] == -1.0 and rec["exit_reason"] == "protective_stop"
    assert rec["r_short"] > 1.0           # 反方向反而赚：方向选择在这笔是负贡献
    assert rec["paired_diff"] < -1.0


def test_no_breakout_event_is_skipped():
    flat_tail = [_bar(k, 101.4, 101.4, 101.5, 101.3) for k in range(1, 20)]
    df = _df(_pre_bars() + flat_tail)
    rec = replay_event(RULE, "TEST", "CPI", T0, df, cap_seconds=CAP_S)
    assert rec["entered"] == 0


def test_simulate_outcome_stop_beats_cap():
    bars = pd.DataFrame([
        {"date": T0 + timedelta(minutes=1), "open": 0.0, "close": 0.0,
         "high": 105.0, "low": 90.0, "volume": 1.0},
    ])
    out = simulate_outcome(bars, entry=100.0, risk=2.0, direction="LONG",
                           entry_time=T0, cap_seconds=3600)
    assert out["r"] == -1.0 and out["exit_reason"] == "protective_stop"


def test_permutation_separates_signal_from_noise():
    strong = permutation_pvalue([0.8] * 12, n_perm=5000, seed=1)
    assert strong["p_value"] < 0.01
    assert verdict(strong["observed"], strong["p_value"]) == "edge_supported"
    noise = permutation_pvalue([0.5, -0.4, 0.3, -0.6, 0.2, -0.1] * 2,
                               n_perm=5000, seed=1)
    assert noise["p_value"] > 0.05
    assert verdict(noise["observed"], noise["p_value"]) == "insufficient_evidence"
    adverse = permutation_pvalue([-0.9] * 12, n_perm=5000, seed=1)
    assert verdict(adverse["observed"], adverse["p_value"]) == "edge_challenged"


def test_run_over_synthetic_archive():
    with tempfile.TemporaryDirectory() as tmp:
        arch = EventDataArchive(tmp, source="synthetic-negctrl",
                                allow_synthetic=True)
        cont = _pre_bars() + _decay_and_breakout() + [
            _bar(16 + i, 102.45 + 0.2 * i, 102.65 + 0.2 * i,
                 102.7 + 0.2 * i, 102.4 + 0.2 * i) for i in range(6)]
        rev = _pre_bars() + _decay_and_breakout() + [
            _bar(16, 102.4, 101.7, 102.45, 101.6),
            _bar(17, 101.7, 101.2, 101.75, 101.2),
            _bar(18, 101.2, 101.2, 101.3, 101.1),
            _bar(19, 101.2, 101.2, 101.3, 101.1),
            _bar(20, 101.2, 101.2, 101.3, 101.1),
            _bar(21, 101.2, 101.2, 101.3, 101.1)]
        contract = {"conId": 0, "secType": "FUT"}
        for name, bars in (("cont", cont), ("rev", rev)):
            eid = f"CPI@2026-08-27-{name}"
            arch.open_event(eid, "CPI", T0, "TEST", contract)
            arch.append_many(eid, "TEST", "bars", bars)
            arch.seal_event(eid, "TEST")
        rep = run(Path(tmp), rules={"TEST": RULE})
        assert rep["events_replayed"] == 2
        assert len(rep["events_skipped"]) == 0
        by = {r["event_id"]: r for r in rep["records"]}
        assert by["CPI@2026-08-27-cont"]["paired_diff"] > 0.9
        assert by["CPI@2026-08-27-rev"]["paired_diff"] < -1.0
        # n=2 时符号翻转检验无法达到 0.05，必须为 insufficient_evidence
        assert rep["verdict"] == "insufficient_evidence"
        assert "TEST" in rep["by_symbol_mean_diff"]


def main() -> int:
    test_engine_fires_on_crafted_tape()
    test_continuation_tape_gives_positive_diff()
    test_reversal_tape_gives_negative_diff()
    test_no_breakout_event_is_skipped()
    test_simulate_outcome_stop_beats_cap()
    test_permutation_separates_signal_from_noise()
    test_run_over_synthetic_archive()
    print("✓ negative-control harness passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
