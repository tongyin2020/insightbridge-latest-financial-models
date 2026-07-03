"""Deterministic, data-free self-checks for the Phase-4 telemetry adapters and
their interaction with the ExecutionQualityGate. No live gateway required."""
from __future__ import annotations

from .telemetry import (
    ExecutionState, RejectRateTracker, spread_bps_from_quote,
    liquidity_score_from_sizes,
)
from .execution_quality_gate import ExecutionQualityGate


def _check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        raise AssertionError(name)


def test_execution_state_from_ticker():
    st = ExecutionState.from_ticker(connected=True, tick_epoch=1000.0,
                                    now_epoch=1000.5, latency_s=0.2,
                                    recent_reject_rate=0.0)
    _check("quote_age computed", abs(st.quote_age_s - 0.5) < 1e-9)
    _check("connected", st.connected)
    # missing tick time -> maximally stale (safe)
    st2 = ExecutionState.from_ticker(True, None, 1000.0, 0.2, 0.0)
    _check("missing tick -> stale", st2.quote_age_s >= 999.0)
    # reject rate clamped to [0,1]
    st3 = ExecutionState.from_ticker(True, 1.0, 1.0, 0.0, 5.0)
    _check("reject rate clamped", st3.recent_reject_rate == 1.0)


def test_gate_consumes_execution_state():
    gate = ExecutionQualityGate()
    good = ExecutionState.from_ticker(True, 100.0, 100.3, 0.2, 0.0)
    _check("healthy state passes gate", gate.evaluate(good).allowed)
    stale = ExecutionState.from_ticker(True, 100.0, 105.0, 0.2, 0.0)
    _check("stale quote blocked", not gate.evaluate(stale).allowed)
    down = ExecutionState(connected=False, quote_age_s=0.1, latency_s=0.1,
                          recent_reject_rate=0.0)
    _check("disconnected blocked", not gate.evaluate(down).allowed)
    slow = ExecutionState.from_ticker(True, 100.0, 100.1, 3.0, 0.0)
    _check("high latency blocked", not gate.evaluate(slow).allowed)


def test_reject_rate_tracker():
    t = RejectRateTracker(window=10, min_samples=5)
    _check("cold start is 0", t.rate() == 0.0)
    for _ in range(4):
        t.record("Filled")
    _check("below min_samples still 0", t.rate() == 0.0)
    t.record("Rejected")
    _check("1/5 rejected", abs(t.rate() - 0.2) < 1e-9)
    t2 = RejectRateTracker(window=4, min_samples=1)
    for s in ("Filled", "Cancelled", "ApiCancelled", "Filled"):
        t2.record(s)
    _check("window counts cancels as rejects", abs(t2.rate() - 0.5) < 1e-9)


def test_spread_and_liquidity():
    _check("spread bps computed",
           abs(spread_bps_from_quote(100.0, 100.1) - 9.995) < 0.01)
    _check("missing quote -> None", spread_bps_from_quote(None, 100.0) is None)
    _check("crossed book -> None", spread_bps_from_quote(100.2, 100.0) is None)
    _check("no sizes -> neutral 0.5",
           liquidity_score_from_sizes(None, None) == 0.5)
    balanced = liquidity_score_from_sizes(100.0, 100.0)
    lopsided = liquidity_score_from_sizes(100.0, 5.0)
    _check("balanced book scores higher than lopsided", balanced > lopsided)
    thin = liquidity_score_from_sizes(1.0, 1.0, ref_size=100.0)
    deep = liquidity_score_from_sizes(100.0, 100.0, ref_size=100.0)
    _check("deep book scores higher than thin", deep > thin)


def main():
    for fn in [test_execution_state_from_ticker, test_gate_consumes_execution_state,
               test_reject_rate_tracker, test_spread_and_liquidity]:
        print(fn.__name__)
        fn()
    print("\nALL V2 TELEMETRY SELF-CHECKS PASSED")


if __name__ == "__main__":
    main()
